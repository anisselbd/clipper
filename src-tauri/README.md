# src-tauri (phase 2, scaffold)

Coquille **Tauri v2** qui empaquette le front Next.js en application desktop, avec le moteur FastAPI lancé en **sidecar PyInstaller**. Non bloquant pour la phase 1 : en dev, on lance `uvicorn` (moteur) et `next dev` (front) directement, sans Tauri.

Bon point de départ : le template [dieharders/example-tauri-v2-python-server-sidecar](https://github.com/dieharders/example-tauri-v2-python-server-sidecar) (Next.js + FastAPI sidecar en Tauri v2).

## Principe

```
+------------------ Application Tauri (.app) ------------------+
|  WebView (front Next.js exporte statiquement, app/out)      |
|        |  HTTP/JSON + SSE sur http://127.0.0.1:8008         |
|        v                                                    |
|  Sidecar : binaire PyInstaller du moteur FastAPI            |
|  (clipper-engine-aarch64-apple-darwin)                      |
+-------------------------------------------------------------+
```

La frontiere front -> moteur reste **exactement** le contrat HTTP de la phase 1. C'est la meme qu'en SaaS (front Vercel -> worker GPU) : rien a jeter.

## Etapes pour completer (phase 2)

1. **Export statique du front** : ajouter `output: "export"` dans `app/next.config.ts` (l'app est 100% client, compatible export). Sortie dans `app/out`, pointee par `frontendDist`.

2. **Construire le sidecar** (binaire unique du moteur) :
   ```bash
   cd engine
   uv run pyinstaller clipper-engine.spec
   # produit dist/clipper-engine ; le copier en :
   #   src-tauri/binaries/clipper-engine-aarch64-apple-darwin
   ```
   Le suffixe target-triple est impose par Tauri pour les `externalBin`.

3. **Initialiser le projet Rust Tauri** (si absent) :
   ```bash
   cargo install create-tauri-app   # ou: npm create tauri-app
   ```
   `Cargo.toml`, `src/main.rs` (spawn + arret propre du sidecar) et `tauri.conf.json` sont fournis ici comme base.

4. **Lancer** :
   ```bash
   cd src-tauri && cargo tauri dev      # dev (front via next dev)
   cd src-tauri && cargo tauri build    # .app/.dmg signe
   ```

## Cycle de vie du sidecar

`src/main.rs` (fourni) montre :
- demarrage du sidecar au lancement de l'app (`app.shell().sidecar("clipper-engine")`),
- attente que `http://127.0.0.1:8008/health` reponde avant d'afficher la fenetre,
- arret propre du process moteur a la fermeture (`on_window_event` / `RunEvent::Exit`), pour ne pas laisser un uvicorn orphelin.

## Notes

- Le moteur ecrit ses donnees dans un data dir utilisateur (cf. `DATA_DIR`). En .app, pointer vers `~/Library/Application Support/clipper`.
- ffmpeg : embarquer un binaire ffmpeg (idealement avec libass pour le chemin sous-titres natif) ou conserver l'overlay PNG si le ffmpeg systeme est minimal.
