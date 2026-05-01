use crate::process::{
    InstallerConfig, InstallerEvent, InstallerProgress, InstallerStage, spawn_update_worker,
};
use eframe::egui;
use egui::{Color32, Frame, Margin, RichText};
use std::sync::Arc;
use std::sync::atomic::{AtomicI32, Ordering};
use std::sync::mpsc;
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

fn stage_color(stage: InstallerStage) -> Color32 {
    match stage {
        InstallerStage::Completed => SUCCESS,
        InstallerStage::Failed => ERROR,
        _ => ACCENT,
    }
}

pub(crate) fn run_gui(config: InstallerConfig) -> i32 {
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
    progress: InstallerProgress,
    rx: mpsc::Receiver<InstallerEvent>,
    exit_code: Arc<AtomicI32>,
    close_at: Option<Instant>,
}

impl UpdaterApp {
    fn new(version: String, rx: mpsc::Receiver<InstallerEvent>, exit_code: Arc<AtomicI32>) -> Self {
        Self {
            version,
            progress: InstallerProgress::starting(),
            rx,
            exit_code,
            close_at: None,
        }
    }

    fn apply_progress(&mut self, mut progress: InstallerProgress) {
        if progress.stage.rank() < self.progress.stage.rank()
            && progress.percent <= self.progress.percent
        {
            return;
        }
        progress.percent = progress.percent.max(self.progress.percent);
        self.progress = progress;
    }

    fn apply_finished(&mut self, exit_code: i32, message: String) {
        self.exit_code.store(exit_code, Ordering::Relaxed);
        if exit_code == 0 {
            self.progress = InstallerProgress::completed(message);
            self.close_at = Some(Instant::now() + Duration::from_millis(1500));
        } else {
            self.progress = InstallerProgress::failed(self.progress.percent, message);
            self.close_at = None;
        }
    }

    fn apply_fatal(&mut self, message: String) {
        self.exit_code.store(1, Ordering::Relaxed);
        self.progress = InstallerProgress::failed(self.progress.percent, message);
        self.close_at = None;
    }

    fn drain_events(&mut self) {
        while let Ok(ev) = self.rx.try_recv() {
            match ev {
                InstallerEvent::Progress(progress) => self.apply_progress(progress),
                InstallerEvent::Finished { exit_code, message } => {
                    self.apply_finished(exit_code, message)
                }
                InstallerEvent::Fatal { message } => self.apply_fatal(message),
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
            .inner_margin(Margin {
                left: 30,
                right: 30,
                top: 28,
                bottom: 20,
            })
            .corner_radius(8.0)
            .fill(BG);

        egui::CentralPanel::default().frame(panel).show(ctx, |ui| {
            ui.label(
                RichText::new("CGS Updater")
                    .size(22.0)
                    .strong()
                    .color(TEXT_PRIMARY),
            );
            ui.add_space(4.0);
            ui.label(
                RichText::new(format!("v{}", self.version))
                    .size(13.0)
                    .color(TEXT_SECONDARY),
            );
            ui.add_space(12.0);
            ui.separator();
            ui.add_space(12.0);
            ui.label(
                RichText::new(&self.progress.status)
                    .size(14.0)
                    .color(stage_color(self.progress.stage)),
            );
            ui.add_space(12.0);
            ui.label(
                RichText::new("Stage progress")
                    .size(12.0)
                    .color(TEXT_SECONDARY),
            );
            ui.add_space(4.0);
            ui.add(
                egui::ProgressBar::new((self.progress.percent as f32 / 100.0).clamp(0.0, 1.0))
                    .fill(stage_color(self.progress.stage))
                    .show_percentage(),
            );
        });

        ctx.request_repaint_after(Duration::from_millis(100));
    }
}
