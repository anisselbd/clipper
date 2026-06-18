# clipper desktop (Tauri v2)

App macOS qui lance le moteur clipper et l'interface en une fenetre, sans terminal. Version **perso, faible risque** : le moteur Python n'est pas embarque (pas de PyInstaller), il est lance depuis `engine/` via `uv`. Prerequis sur la machine : **uv, Python 3.12, ffmpeg** (deja installes ici). LLM optionnel : `llama-server` sur :8080.

## Lancer

Depuis `src-tauri/` :

```bash
# Dev (fenetre + rechargement du front)
npx @tauri-apps/cli@latest dev

# Build : produit clipper.app
npx @tauri-apps/cli@latest build
# -> src-tauri/target/release/bundle/macos/clipper.app
```

Le `.app` n'est pas signe : au premier lancement, clic droit puis "Ouvrir" (ou `xattr -dr com.apple.quarantine clipper.app`).

## Comment ca marche

- **`src/lib.rs`** demarre le moteur au lancement : `uv run clipper-api` dans `engine/` (API FastAPI sur :8008). Le PATH est enrichi (Homebrew + `~/.local/bin`) car une app lancee depuis le Finder n'herite pas du PATH du shell.
- **Front** : export statique Next (`app/out`, `next.config.ts` -> `output: "export"`), charge par la WebView. Il parle a l'API en HTTP/JSON sur localhost (CORS `tauri://localhost` autorise cote moteur).
- **Cycle de vie** : a la fermeture (fenetre / Cmd+Q) les handlers Tauri arretent le moteur. En plus, un **watchdog parent** cote moteur (`CLIPPER_PARENT_PID`) l'auto-termine si l'app disparait pour une autre raison (crash, kill) : pas de `uvicorn` orphelin.

## Limites de cette version (et la suite)

- **Specifique a cette machine** : le chemin de `engine/` est fige a la compilation (`CARGO_MANIFEST_DIR/../engine`). Si tu deplaces le repo, recompile (ou pose `CLIPPER_ENGINE_DIR`).
- **Pas autonome** : il faut uv + Python + ffmpeg sur la machine.

Pour un `.app` **distribuable** a n'importe qui (la piste suivante, plus dure) : embarquer le moteur en binaire (PyInstaller, caveats mediapipe/ctranslate2 dans `engine/clipper-engine.spec`) + un ffmpeg, puis signer et notariser. Bon point de depart : le template [dieharders/example-tauri-v2-python-server-sidecar](https://github.com/dieharders/example-tauri-v2-python-server-sidecar).
