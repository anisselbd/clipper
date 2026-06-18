# clipper

Application desktop de clipping video **local-first** : une URL en entree, des clips verticaux 9:16 sous-titres mot a mot en sortie. Le moteur Python (yt-dlp, faster-whisper, MediaPipe, ffmpeg VideoToolbox) tourne en local ; une UI Next.js le pilote via HTTP.

L'architecture est pensee pour devenir un SaaS **sans rien jeter** : la frontiere front -> moteur est du HTTP/JSON pur (la meme qu'on aura entre un front Vercel et un worker GPU), et chaque point de bascule local/cloud est derriere une interface de provider.

## Monorepo

```
clipper/
  engine/        # moteur Python (pipeline + providers + API FastAPI)
    src/clipper/
      pipeline.py, download.py, transcribe.py, segment.py,
      reframe.py, captions.py, render.py, preflight.py
      providers/   # storage/ llm/ encoder/ jobstore/  (base + local + stub cloud)
      api/         # server.py routes.py worker.py events.py schemas.py
  app/           # front Next.js + React (accueil / progression SSE / resultats)
  src-tauri/     # coquille Tauri v2 (phase 2, scaffold)
```

## Prerequis

- macOS Apple Silicon, **Python 3.12**, **uv**, **Node 20+**, **ffmpeg** (`brew install ffmpeg`).
- Optionnel : un **serveur LLM local** compatible OpenAI pour la selection (par defaut `llama-server` sur `:8080`). Sans lui, le moteur bascule sur une selection heuristique (100% hors-ligne).

Le moteur fait un **preflight** au demarrage (`GET /health`) : il detecte libass, les encodeurs (VideoToolbox/libx264), MediaPipe et la presence du LLM, et choisit ses chemins automatiquement. Rien n'est suppose, tout est verifie.

## Lancer en dev (phase 1)

Deux process, dans deux terminaux :

```bash
# 1. Moteur (API FastAPI sur http://localhost:8008)
cd engine
uv sync
uv run clipper-api          # ou : uv run uvicorn clipper.api.server:app --reload --port 8008

# 2. Front (http://localhost:3000)
cd app
npm install
npm run dev
```

Ouvrir http://localhost:3000, coller une URL, generer.

LLM optionnel pour une meilleure selection :

```bash
llama-server -m ./qwen3.gguf --host 127.0.0.1 --port 8080 -c 8192 -ngl 99 --jinja
```

Le front detecte automatiquement le backend (badge "selection LLM / heuristique").

## Contrat HTTP (front <-> moteur)

| Methode | Route | Role |
|--------|-------|------|
| `POST` | `/jobs` | cree un job `{url, num_clips, lang, whisper_model}`, lance le pipeline en tache de fond |
| `GET` | `/jobs/{id}` | statut + etape + progression |
| `GET` | `/jobs/{id}/events` | flux **SSE** de progression (etape, %, clips au fil de l'eau) |
| `GET` | `/jobs/{id}/clips` | liste des clips (titre, score, duree, url, vignette) |
| `GET` | `/clips/{id}/file` | sert le mp4 |
| `GET` | `/files/{key}` | sert un fichier du StorageProvider (URL renvoyee au front) |
| `POST` | `/jobs/{id}/reveal` | ouvre le dossier de sortie (desktop) |
| `GET` | `/health` | rapport de preflight |

Le front lit **toujours** un champ `url` pour les fichiers (jamais un chemin local), pour rester identique en cloud.

## Les 4 providers (coutures SaaS)

| Interface | Impl locale (defaut) | Stub cloud (phase 2) |
|-----------|----------------------|----------------------|
| **StorageProvider** | fichiers sous un data dir, servis en localhost | R2/S3 + URL presignee |
| **LLMProvider** | llama-server (sortie structuree json_schema, thinking-off, temperature 0, reessais) + fallback heuristique | LLM heberge |
| **EncoderProvider** | VideoToolbox/libx264 + libass ou overlay PNG (choisi par le preflight) | NVENC (worker GPU) |
| **JobStore** | SQLite | Supabase/Postgres |

Le front et l'API ne connaissent que les interfaces. Passer en SaaS = implementer les stubs, sans toucher au front ni au contrat HTTP.

## Briques agnostiques (lecons RETEX)

- **Sous-titres** : libass natif si dispo, sinon overlay PNG (Pillow + `concat`/`overlay`). Auto-detecte.
- **Visage** : MediaPipe Tasks, sinon OpenCV Haar.
- **Selection** : LLM local (JSON force par grammaire), sinon heuristique. Degradation gracieuse si le LLM est absent.

## Tests

```bash
cd engine && uv run pytest -q     # pipeline, providers, API helpers
cd app && npm run build           # types + build front
```

## Phase 2 (scaffold, non bloquant)

- `src-tauri/` : empaquetage Tauri v2 + moteur en sidecar PyInstaller (voir `src-tauri/README.md`).
- Stubs cloud des 4 providers (`engine/src/clipper/providers/*/cloud_stub.py`).
- Le moteur (`engine/`) garde son CLI autonome : `uv run clipper <url>`.

Details du moteur et du pipeline : `engine/README.md`.
