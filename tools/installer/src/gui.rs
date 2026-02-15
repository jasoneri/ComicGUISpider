use crate::process::{spawn_update_worker, InstallerConfig, InstallerEvent};
use eframe::egui;
use egui::{Color32, Frame, Margin, RichText};
use std::sync::atomic::{AtomicI32, Ordering};
use std::sync::mpsc;
use std::sync::Arc;
use std::time::{Duration, Instant};

const BG: Color32 = Color32::from_rgb(26, 26, 46);
const TEXT_PRIMARY: Color32 = Color32::from_rgb(226, 226, 234);
const TEXT_SECONDARY: Color32 = Color32::from_rgb(136, 136, 160);
const ACCENT: Color32 = Color32::from_rgb(96, 165, 250);
const SUCCESS: Color32 = Color32::from_rgb(74, 222, 128);
const ERROR: Color32 = Color32::from_rgb(248, 113, 113);

fn configure_visuals(ctx: &egui::Context) {
    ctx.set_visuals(egui::Visuals {
        panel_fill: BG,
        window_fill: BG,
        override_text_color: Some(TEXT_PRIMARY),
        ..egui::Visuals::dark()
    });
}

fn status_color(status: &str) -> Color32 {
    let s = status.to_ascii_lowercase();
    if s.contains("fail") || s.contains("error") {
        ERROR
    } else if s.contains("installed") || s.contains("success") || s.contains("restart") || s.contains("done") {
        SUCCESS
    } else if s.contains("download") || s.contains("resolv") || s.contains("install") {
        ACCENT
    } else {
        TEXT_SECONDARY
    }
}

pub fn run_gui(config: InstallerConfig) -> i32 {
    let (tx, rx) = mpsc::channel::<InstallerEvent>();
    let _worker = spawn_update_worker(config.clone(), tx);
    let exit_code = Arc::new(AtomicI32::new(1));
    let exit_code_app = Arc::clone(&exit_code);

    let options = eframe::NativeOptions {
        viewport: egui::ViewportBuilder::default()
            .with_inner_size([480.0, 220.0])
            .with_resizable(false),
        ..Default::default()
    };

    let ver = config.version.clone();
    let result = eframe::run_native(
        "CGS Updater",
        options,
        Box::new(move |cc| {
            configure_visuals(&cc.egui_ctx);
            Ok(Box::new(UpdaterApp::new(ver, rx, exit_code_app)))
        }),
    );

    if result.is_err() {
        return 1;
    }
    exit_code.load(Ordering::Relaxed)
}

struct UpdaterApp {
    version: String,
    status: String,
    progress: u8,
    rx: mpsc::Receiver<InstallerEvent>,
    exit_code: Arc<AtomicI32>,
    close_at: Option<Instant>,
}

impl UpdaterApp {
    fn new(
        version: String,
        rx: mpsc::Receiver<InstallerEvent>,
        exit_code: Arc<AtomicI32>,
    ) -> Self {
        Self {
            version,
            status: "Preparing update...".into(),
            progress: 0,
            rx,
            exit_code,
            close_at: None,
        }
    }

    fn drain_events(&mut self) {
        while let Ok(ev) = self.rx.try_recv() {
            match ev {
                InstallerEvent::Progress { percent, status } => {
                    self.progress = percent.min(100);
                    self.status = status;
                }
                InstallerEvent::Finished { exit_code, message } => {
                    self.exit_code.store(exit_code, Ordering::Relaxed);
                    self.status = message;
                    if exit_code == 0 {
                        self.progress = 100;
                        self.close_at = Some(Instant::now() + Duration::from_millis(1500));
                    }
                }
                InstallerEvent::Fatal { message } => {
                    self.exit_code.store(1, Ordering::Relaxed);
                    self.status = message;
                }
            }
        }
    }
}

impl eframe::App for UpdaterApp {
    fn update(&mut self, ctx: &egui::Context, _frame: &mut eframe::Frame) {
        self.drain_events();

        if let Some(t) = self.close_at {
            if Instant::now() >= t {
                ctx.send_viewport_cmd(egui::ViewportCommand::Close);
                return;
            }
            ctx.request_repaint_after(Duration::from_millis(50));
        }

        let panel = Frame::new()
            .inner_margin(Margin { left: 30, right: 30, top: 28, bottom: 20 })
            .corner_radius(8.0)
            .fill(BG);

        egui::CentralPanel::default().frame(panel).show(ctx, |ui| {
            ui.label(RichText::new("CGS Updater").size(22.0).strong().color(TEXT_PRIMARY));
            ui.add_space(4.0);
            ui.label(RichText::new(format!("v{}", self.version)).size(13.0).color(TEXT_SECONDARY));
            ui.add_space(12.0);
            ui.separator();
            ui.add_space(12.0);
            ui.label(RichText::new(&self.status).size(14.0).color(status_color(&self.status)));
            ui.add_space(16.0);
            ui.add(
                egui::ProgressBar::new(self.progress as f32 / 100.0)
                    .fill(ACCENT)
                    .show_percentage(),
            );
        });

        ctx.request_repaint_after(Duration::from_millis(100));
    }
}
