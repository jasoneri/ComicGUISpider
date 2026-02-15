use crate::args::CliArgs;
use crate::version::build_install_args;
use regex::Regex;
use std::fs::{self, File, OpenOptions};
use std::io::{self, BufRead, BufReader, Read, Write};
use std::path::{Path, PathBuf};
use std::process::{Command, Stdio};
use std::sync::mpsc::Sender;
use std::sync::{Arc, LazyLock, Mutex};
use std::thread;
use std::time::Duration;

#[derive(Debug, Clone)]
pub struct InstallerConfig {
    pub uv_exc: PathBuf,
    pub version: String,
    pub index_url: String,
    pub uv_tool_dir: PathBuf,
    pub uv_tool_bin_dir: PathBuf,
}

#[derive(Debug, Clone)]
pub enum InstallerEvent {
    Progress { percent: u8, status: String },
    Finished { exit_code: i32, message: String },
    Fatal { message: String },
}

impl InstallerConfig {
    pub fn from_args(args: &CliArgs) -> Self {
        let uv_tool_dir = if args.uv_tool_dir.is_empty() {
            std::env::var("UV_TOOL_DIR")
                .map(PathBuf::from)
                .unwrap_or_else(|_| std::env::current_dir().unwrap_or_else(|_| ".".into()))
        } else {
            PathBuf::from(&args.uv_tool_dir)
        };

        let uv_tool_bin_dir = if args.uv_tool_bin_dir.is_empty() {
            std::env::var("UV_TOOL_BIN_DIR")
                .map(PathBuf::from)
                .unwrap_or_else(|_| uv_tool_dir.join("bin"))
        } else {
            PathBuf::from(&args.uv_tool_bin_dir)
        };

        Self {
            uv_exc: PathBuf::from(&args.uv_exc),
            version: args.version.clone(),
            index_url: args.index_url.clone(),
            uv_tool_dir,
            uv_tool_bin_dir,
        }
    }

    pub fn log_path(&self) -> PathBuf {
        self.uv_tool_dir.join("cgs_update.log")
    }

    pub fn install_args(&self) -> Vec<String> {
        build_install_args(&self.version, &self.index_url)
    }
}

pub fn cleanup_stale_dirs(config: &InstallerConfig) -> io::Result<()> {
    if !config.uv_tool_dir.exists() {
        return Ok(());
    }
    for entry in fs::read_dir(&config.uv_tool_dir)? {
        let entry = entry?;
        let path = entry.path();
        if !path.is_dir() {
            continue;
        }
        if let Some(name) = path.file_name().and_then(|n| n.to_str()) {
            if name.starts_with("comicguispider_old") {
                let _ = fs::remove_dir_all(&path);
            }
        }
    }
    Ok(())
}

pub fn wait_for_parent_exit(parent_pid: u32, timeout_ms: u32) {
    if parent_pid == 0 {
        return;
    }

    #[cfg(windows)]
    {
        use windows::Win32::Foundation::CloseHandle;
        use windows::Win32::System::Threading::{
            OpenProcess, WaitForSingleObject, PROCESS_SYNCHRONIZE,
        };

        unsafe {
            if let Ok(handle) = OpenProcess(PROCESS_SYNCHRONIZE, false, parent_pid) {
                let _ = WaitForSingleObject(handle, timeout_ms);
                let _ = CloseHandle(handle);
            }
        }
        thread::sleep(Duration::from_secs(1));
    }

    #[cfg(not(windows))]
    {
        let _ = timeout_ms;
    }
}

pub fn run_update_cli(config: &InstallerConfig) -> i32 {
    let logger = open_log(&config.log_path());
    log_msg(&logger, "CLI mode started");

    let args = config.install_args();
    log_msg(
        &logger,
        &format!("Running: {} {}", config.uv_exc.display(), args.join(" ")),
    );

    let exit_code = match Command::new(&config.uv_exc)
        .args(&args)
        .stdout(Stdio::inherit())
        .stderr(Stdio::inherit())
        .env("UV_TOOL_DIR", &config.uv_tool_dir)
        .env("UV_TOOL_BIN_DIR", &config.uv_tool_bin_dir)
        .status()
    {
        Ok(status) => status.code().unwrap_or(1),
        Err(err) => {
            log_msg(&logger, &format!("Failed to start uv: {err}"));
            eprintln!("Failed to start uv: {err}");
            return 1;
        }
    };

    if exit_code == 0 {
        println!("Update successful, restarting...");
        log_msg(&logger, "Update success, restarting");
        if let Err(err) = restart_cgs(config) {
            log_msg(&logger, &format!("Restart failed: {err}"));
            eprintln!("Restart failed: {err}");
            return 1;
        }
    } else {
        log_msg(&logger, &format!("Update failed with code {exit_code}"));
        eprintln!("Update failed (code: {exit_code})");
    }
    exit_code
}

pub fn spawn_update_worker(
    config: InstallerConfig,
    tx: Sender<InstallerEvent>,
) -> thread::JoinHandle<()> {
    thread::spawn(move || {
        if let Err(err) = run_update_worker(&config, &tx) {
            let _ = tx.send(InstallerEvent::Fatal {
                message: format!("Update process error: {err}"),
            });
        }
    })
}

fn run_update_worker(config: &InstallerConfig, tx: &Sender<InstallerEvent>) -> io::Result<()> {
    let logger = open_log(&config.log_path());
    let args = config.install_args();

    log_msg(
        &logger,
        &format!(
            "GUI mode: {} {}",
            config.uv_exc.display(),
            args.join(" ")
        ),
    );
    let _ = tx.send(InstallerEvent::Progress {
        percent: 5,
        status: "Starting update...".into(),
    });

    let mut child = Command::new(&config.uv_exc)
        .args(&args)
        .stdout(Stdio::piped())
        .stderr(Stdio::piped())
        .env("UV_TOOL_DIR", &config.uv_tool_dir)
        .env("UV_TOOL_BIN_DIR", &config.uv_tool_bin_dir)
        .spawn()?;

    let stdout = child.stdout.take();
    let stderr = child.stderr.take();

    let lg1 = Arc::clone(&logger);
    let tx1 = tx.clone();
    let t1 = thread::spawn(move || {
        if let Some(r) = stdout {
            stream_lines(r, &lg1, &tx1);
        }
    });

    let lg2 = Arc::clone(&logger);
    let tx2 = tx.clone();
    let t2 = thread::spawn(move || {
        if let Some(r) = stderr {
            stream_lines(r, &lg2, &tx2);
        }
    });

    let status = child.wait()?;
    let _ = t1.join();
    let _ = t2.join();
    let code = status.code().unwrap_or(1);

    if code == 0 {
        let _ = tx.send(InstallerEvent::Progress {
            percent: 100,
            status: "Installed. Restarting...".into(),
        });
        match restart_cgs(config) {
            Ok(()) => {
                log_msg(&logger, "Restart launched");
                let _ = tx.send(InstallerEvent::Finished {
                    exit_code: 0,
                    message: "Update successful. Restarting...".into(),
                });
            }
            Err(err) => {
                log_msg(&logger, &format!("Restart failed: {err}"));
                let _ = tx.send(InstallerEvent::Finished {
                    exit_code: 1,
                    message: format!("Update OK but restart failed: {err}"),
                });
            }
        }
    } else {
        log_msg(&logger, &format!("Update failed with code {code}"));
        let _ = tx.send(InstallerEvent::Finished {
            exit_code: code,
            message: format!("Update failed (code: {code})"),
        });
    }
    Ok(())
}

fn stream_lines<R: Read>(reader: R, logger: &Arc<Mutex<File>>, tx: &Sender<InstallerEvent>) {
    for line in BufReader::new(reader).lines() {
        let Ok(line) = line else { continue };
        log_msg(logger, &line);
        if let Some(ev) = parse_progress(&line) {
            let _ = tx.send(ev);
        }
    }
}

static RE_RESOLVED: LazyLock<Regex> =
    LazyLock::new(|| Regex::new(r"Resolved (\d+) package").unwrap());
static RE_DL_STEP: LazyLock<Regex> =
    LazyLock::new(|| Regex::new(r"\((\d+)/(\d+)\)").unwrap());
static RE_DOWNLOADED: LazyLock<Regex> =
    LazyLock::new(|| Regex::new(r"Downloaded (\d+) package").unwrap());
static RE_INSTALLED: LazyLock<Regex> =
    LazyLock::new(|| Regex::new(r"Installed (\d+) package").unwrap());

fn parse_progress(line: &str) -> Option<InstallerEvent> {
    if line.contains("Resolved") {
        if let Some(caps) = RE_RESOLVED.captures(line) {
            return Some(InstallerEvent::Progress {
                percent: 15,
                status: format!("Resolved ({})", &caps[1]),
            });
        }
    } else if let Some(caps) = RE_DL_STEP.captures(line) {
        let cur: u32 = caps[1].parse().unwrap_or(0);
        let tot: u32 = caps[2].parse().unwrap_or(1).max(1);
        let pct = (15 + cur * 60 / tot).min(75) as u8;
        return Some(InstallerEvent::Progress {
            percent: pct,
            status: format!("Downloading ({cur}/{tot})"),
        });
    } else if line.contains("Downloaded") {
        if let Some(caps) = RE_DOWNLOADED.captures(line) {
            return Some(InstallerEvent::Progress {
                percent: 75,
                status: format!("Downloaded ({})", &caps[1]),
            });
        }
    } else if line.contains("Installing") {
        return Some(InstallerEvent::Progress {
            percent: 85,
            status: "Installing...".into(),
        });
    } else if line.contains("Installed") {
        let n = RE_INSTALLED
            .captures(line)
            .map(|c| c[1].to_string())
            .unwrap_or_default();
        let status = if n.is_empty() {
            "Installed".into()
        } else {
            format!("Installed ({n})")
        };
        return Some(InstallerEvent::Progress {
            percent: 100,
            status,
        });
    }
    None
}

fn restart_cgs(config: &InstallerConfig) -> io::Result<()> {
    Command::new(&config.uv_exc)
        .args(["tool", "run", "--from", "comicguispider", "cgs"])
        .env("UV_TOOL_DIR", &config.uv_tool_dir)
        .env("UV_TOOL_BIN_DIR", &config.uv_tool_bin_dir)
        .stdout(Stdio::null())
        .stderr(Stdio::null())
        .spawn()
        .map(|_| ())
}

fn open_log(path: &Path) -> Arc<Mutex<File>> {
    let file = OpenOptions::new()
        .create(true)
        .append(true)
        .open(path)
        .unwrap_or_else(|_| {
            OpenOptions::new()
                .create(true)
                .append(true)
                .open("cgs_update.log")
                .expect("cannot open any log file")
        });
    Arc::new(Mutex::new(file))
}

fn log_msg(logger: &Arc<Mutex<File>>, msg: &str) {
    if let Ok(mut f) = logger.lock() {
        let _ = writeln!(f, "{msg}");
    }
}
