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

/// Nettoie un nom de fichier (garde lettres/chiffres/espace/-/_/.).
fn sanitize_filename(name: &str) -> String {
    let mut out: String = name
        .chars()
        .map(|c| if c.is_alphanumeric() || " -_.".contains(c) { c } else { '_' })
        .collect();
    out = out.trim().to_string();
    if out.is_empty() {
        out = "clip".to_string();
    }
    if !out.to_lowercase().ends_with(".mp4") {
        out.push_str(".mp4");
    }
    out
}

/// Enregistre un clip (deja sur disque) dans ~/Downloads puis le revele dans le
/// Finder. Evite la navigation du webview (qui piegerait l'utilisateur sur la
/// video plein ecran). Renvoie le chemin de destination.
#[tauri::command]
fn save_clip(src: String, name: String) -> Result<String, String> {
    let src_path = PathBuf::from(&src);
    if !src_path.exists() {
        return Err(format!("Fichier introuvable : {src}"));
    }
    let home = std::env::var("HOME").map_err(|_| "HOME introuvable".to_string())?;
    let downloads = PathBuf::from(&home).join("Downloads");
    let dest_dir = if downloads.is_dir() { downloads } else { PathBuf::from(&home) };
    let dest = dest_dir.join(sanitize_filename(&name));
    std::fs::copy(&src_path, &dest).map_err(|e| format!("Copie echouee : {e}"))?;
    // Revele le fichier dans le Finder (selectionne).
    let _ = Command::new("open").arg("-R").arg(&dest).spawn();
    log::info!("Clip enregistre : {:?}", dest);
    Ok(dest.to_string_lossy().to_string())
}

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
        .invoke_handler(tauri::generate_handler![save_clip])
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
