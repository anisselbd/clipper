// SCAFFOLD PHASE 2 (non compile en phase 1).
//
// Coquille Tauri v2 : demarre le moteur FastAPI en sidecar au lancement, attend
// que /health reponde, puis arrete proprement le process a la fermeture.
// A completer avec `cargo tauri init` (deps + capabilities). Voir ../README.md.

use std::sync::Mutex;
use tauri::{Manager, RunEvent, WindowEvent};
use tauri_plugin_shell::process::CommandChild;
use tauri_plugin_shell::ShellExt;

/// Garde le handle du process moteur pour pouvoir le tuer a la sortie.
struct EngineProcess(Mutex<Option<CommandChild>>);

fn main() {
    tauri::Builder::default()
        .plugin(tauri_plugin_shell::init())
        .manage(EngineProcess(Mutex::new(None)))
        .setup(|app| {
            // Lance le binaire PyInstaller du moteur (externalBin de tauri.conf.json).
            let sidecar = app.shell().sidecar("clipper-engine")?;
            let (mut _rx, child) = sidecar.spawn()?;
            app.state::<EngineProcess>()
                .0
                .lock()
                .unwrap()
                .replace(child);
            // TODO : poller http://127.0.0.1:8008/health avant d'afficher la fenetre
            // pour eviter un flash "API indisponible" au demarrage.
            Ok(())
        })
        .on_window_event(|window, event| {
            if let WindowEvent::Destroyed = event {
                kill_engine(window.app_handle());
            }
        })
        .build(tauri::generate_context!())
        .expect("erreur de construction Tauri")
        .run(|app, event| {
            if let RunEvent::Exit = event {
                kill_engine(app);
            }
        });
}

fn kill_engine(app: &tauri::AppHandle) {
    if let Some(child) = app.state::<EngineProcess>().0.lock().unwrap().take() {
        let _ = child.kill();
    }
}
