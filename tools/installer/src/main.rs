mod args;
mod gui;
mod process;
mod version;

use args::CliArgs;
use clap::Parser;
use process::{cleanup_stale_dirs, run_update_cli, wait_for_parent_exit, InstallerConfig};

fn main() {
    let args = CliArgs::parse();
    let config = InstallerConfig::from_args(&args);

    wait_for_parent_exit(args.parent_pid, 30_000);
    if let Err(err) = cleanup_stale_dirs(&config) {
        eprintln!("stale cleanup: {err}");
    }

    let exit_code = if args.no_gui {
        run_update_cli(&config)
    } else {
        gui::run_gui(config)
    };

    std::process::exit(exit_code);
}
