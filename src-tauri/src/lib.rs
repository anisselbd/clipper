// App desktop clipper : coquille Tauri qui demarre le moteur FastAPI local
// (via uv) au lancement, et l'arrete proprement a la fermeture.
//
// Version "perso, faible risque" : le moteur n'est pas bundle (PyInstaller), il
// est lance depuis le dossier engine/ du repo (chemin bake a la compilation).
// Prerequis machine : uv, Python 3.12, ffmpeg installes (deja le cas ici).

use std::path::PathBuf;
use std::process::{Child, Command};
use std::sync::Mutex;
use tauri::Manager;

struct EngineProcess(Mutex<Option<Child>>);

/// Dossier du moteur Python. Surchargeable par CLIPPER_ENGINE_DIR, sinon le
/// dossier engine/ du repo, resolu a la compilation.
fn engine_dir() -> PathBuf {
    if let Ok(d) = std::env::var("CLIPPER_ENGINE_DIR") {
        return PathBuf::from(d);
    }
    PathBuf::from(env!("CARGO_MANIFEST_DIR"))
        .join("..")
        .join("engine")
}

/// PATH enrichi : une app lancee depuis le Finder n'herite pas du PATH du shell,
/// donc on ajoute explicitement Homebrew et ~/.local/bin (uv, ffmpeg).
fn enriched_path() -> String {
    let extra = "/opt/homebrew/bin:/Users/anisse/.local/bin:/usr/local/bin";
    match std::env::var("PATH") {
        Ok(p) => format!("{extra}:{p}"),
        Err(_) => format!("{extra}:/usr/bin:/bin:/usr/sbin:/sbin"),
    }
}

fn start_engine() -> Option<Child> {
    let dir = engine_dir();
    let uv_abs = "/Users/anisse/.local/bin/uv";
    let uv = if std::path::Path::new(uv_abs).exists() {
        uv_abs.to_string()
    } else {
        "uv".to_string()
    };
    match Command::new(&uv)
        .args(["run", "clipper-api"])
        .current_dir(&dir)
        .env("PATH", enriched_path())
        // Le moteur s'auto-termine si cette app disparait (watchdog parent).
        .env("CLIPPER_PARENT_PID", std::process::id().to_string())
        .spawn()
    {
        Ok(child) => {
            log::info!("Moteur clipper demarre (pid {}) depuis {:?}", child.id(), dir);
            Some(child)
        }
        Err(e) => {
            log::error!("Echec du demarrage du moteur ({}): {:?}", e, dir);
            None
        }
    }
}

fn stop_engine(app: &tauri::AppHandle) {
    if let Some(mut child) = app.state::<EngineProcess>().0.lock().unwrap().take() {
        let _ = child.kill();
        let _ = child.wait();
        log::info!("Moteur clipper arrete.");
    }
}

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    tauri::Builder::default()
        .plugin(tauri_plugin_log::Builder::default().level(log::LevelFilter::Info).build())
        .manage(EngineProcess(Mutex::new(start_engine())))
        .on_window_event(|window, event| {
            if matches!(event, tauri::WindowEvent::Destroyed | tauri::WindowEvent::CloseRequested { .. }) {
                stop_engine(window.app_handle());
            }
        })
        .build(tauri::generate_context!())
        .expect("erreur de construction de l'application Tauri")
        .run(|app, event| {
            if matches!(event, tauri::RunEvent::ExitRequested { .. } | tauri::RunEvent::Exit) {
                stop_engine(app);
            }
        });
}
