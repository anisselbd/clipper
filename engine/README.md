# clipper

Moteur de clipping vidéo **local-first** dans l'esprit d'Opus Clip, conçu pour tourner sur un MacBook Pro Apple Silicon (M4). On donne une URL (YouTube en priorité), l'outil télécharge la vidéo, repère les meilleurs moments, les découpe en clips verticaux 9:16, recadre sur le visage dominant et incruste des sous-titres mot à mot générés à partir de l'audio réel.

## Ce que l'outil fait et ne fait pas

L'outil **découpe de l'existant**, il ne crée rien :

- Pas de génération de script, pas d'histoire inventée.
- Pas de TTS ni de voix off : la voix des clips est celle de la vidéo source.
- Pas de stock footage, pas d'images IA, pas de musique ajoutée.

Le LLM sert **uniquement à sélectionner** les segments les plus forts en lisant le transcript réel. Il renvoie des timestamps, jamais du texte inventé.

## Pipeline

1. **download** : `yt-dlp` récupère la vidéo source (mp4, cache local).
2. **transcribe** : `faster-whisper` produit un transcript avec timestamps mot à mot (brique non négociable).
3. **segment** : le transcript est envoyé à un LLM qui renvoie les N meilleurs segments (sélection pure). Fallback heuristique si le LLM est injoignable.
4. **cut + render** : `ffmpeg` extrait chaque plage.
5. **reframe** : conversion 16:9 vers 9:16 centrée sur le visage dominant (MediaPipe), par scène (PySceneDetect), avec repli crop centré.
6. **captions** : génération d'un fichier ASS karaoké (mot surligné au moment où il est prononcé).
7. **render** : `ffmpeg` applique crop + sous-titres, encode en 1080x1920 via `h264_videotoolbox`, sort un mp4 par clip plus un `meta.json`, et un `output/index.json` récapitulatif.

## Prérequis

- **macOS Apple Silicon** (testé sur M4, macOS 26).
- **Python 3.12** (ne pas utiliser 3.13, certaines dépendances ML ne suivent pas).
- **uv** pour la gestion d'environnement : `curl -LsSf https://astral.sh/uv/install.sh | sh`
- **ffmpeg** avec `h264_videotoolbox` : `brew install ffmpeg` (vérifier avec `ffmpeg -encoders | grep videotoolbox`).
- **Un serveur LLM local optionnel** exposant une API compatible OpenAI. Par défaut `llama-server` (llama.cpp) servant Qwen3 sur `http://localhost:8080/v1`.

Exemple de lancement du serveur LLM (à adapter au chemin de ton modèle) :

```bash
llama-server -m ./qwen3.gguf --host 127.0.0.1 --port 8080 -c 8192 -ngl 99 --jinja
```

L'option `--jinja` est nécessaire pour les modèles Qwen3 (template de chat). Le mode raisonnement (thinking) est **désactivé automatiquement** par le pipeline (`chat_template_kwargs.enable_thinking=false`) pour obtenir un JSON direct et rapide ; sans cela, Qwen3 consomme tout son budget de tokens à raisonner et ne renvoie rien d'exploitable. La sélection se fait à température 0 avec réessais (`LLM_RETRIES`) pour la fiabilité du format.

Si aucun serveur LLM n'est joignable, le pipeline bascule automatiquement sur une **sélection heuristique** et reste pleinement fonctionnel hors-ligne (la sélection est simplement moins fine).

## Installation

```bash
git clone <repo> clipper && cd clipper
uv sync
cp .env.example .env   # puis ajuster si besoin
```

`uv sync` crée l'environnement et installe les dépendances épinglées.

## Utilisation

```bash
uv run clipper "https://www.youtube.com/watch?v=XXXXXXXXXXX"
```

Options :

```bash
uv run clipper <url> \
  --clips 8 \                # nombre de clips (défaut 8)
  --lang fr \                # langue de transcription (défaut fr)
  --whisper-model small \    # tiny | base | small | medium | large-v3
  --provider local_llm \     # local_llm (défaut) ou anthropic (stub)
  --output output \
  -v                         # logs détaillés
```

### Résultat

```
output/
  index.json            # récapitulatif (source, langue, liste des clips)
  clip_00/
    clip.mp4            # 1080x1920, sous-titres incrustés
    subs.ass            # sous-titres karaoké générés
    meta.json           # titre, score, url source, start/end, résolution
  clip_01/
  ...
```

Tout est configurable par variables d'environnement (voir `.env.example`).

## Configuration

Les réglages se font dans `.env` (voir `.env.example` pour la liste complète) :

- **LLM** : `LLM_BASE_URL`, `LLM_MODEL`, `LLM_API_KEY`, `LLM_PROVIDER`.
- **Transcription** : `WHISPER_MODEL`, `WHISPER_DEVICE`, `WHISPER_COMPUTE_TYPE`, `LANG_CODE`.
- **Sélection** : `CLIPS`, `MIN_DURATION`, `MAX_DURATION`.
- **Recadrage** : `PER_SCENE_REFRAME`, `SCENE_THRESHOLD`, `FACE_CONFIDENCE`, `SAMPLES_PER_SCENE`.
- **Rendu** : `FPS`, `VIDEO_ENCODER`, `VIDEO_BITRATE`.
- **API / serveur** : `API_HOST`, `API_PORT` (8008), `PUBLIC_BASE_URL`, `WORKER_CONCURRENCY`, `DATA_DIR`.

## API (serveur)

Le moteur expose aussi une API FastAPI consommee par le front (voir le README racine du monorepo) :

```bash
uv run clipper-api          # http://localhost:8008
# ou : uv run uvicorn clipper.api.server:app --reload --port 8008
```

Routes : `POST /jobs`, `GET /jobs/{id}`, `GET /jobs/{id}/events` (SSE), `GET /jobs/{id}/clips`, `GET /clips/{id}/file`, `GET /health`. Un `preflight` au demarrage detecte les capacites (libass, encodeurs, MediaPipe, LLM) et le code choisit ses chemins dessus. Les 4 points de bascule local/cloud sont derriere des providers (`storage/`, `llm/`, `encoder/`, `jobstore/`).

## Tests

```bash
uv run pytest -q
```

Couvre le parsing robuste de la réponse LLM, l'alignement des segments sur les frontières de phrase, le calcul du crop 9:16 et la génération ASS.

## Sous-titres : deux chemins de rendu

Le surlignage mot à mot est généré à partir des timestamps réels. Le rendu s'adapte automatiquement aux capacités de ton ffmpeg :

- **ffmpeg avec libass** : incrustation native du fichier ASS karaoké (chemin canonique, le plus rapide).
- **ffmpeg sans libass** (cas des builds Homebrew minimaux) : bascule automatique sur un **overlay d'images PNG** rendu avec Pillow, incrusté via le démultiplexeur `concat` et le filtre `overlay` (cœur de ffmpeg). Aucune dépendance système, 100 % hors-ligne. Le fichier `subs.ass` reste produit dans chaque dossier de clip comme artefact portable.

Le pipeline détecte le backend disponible au lancement (ligne de log « Sous-titres : ... »). Pour forcer le chemin libass natif, installe un ffmpeg compilé avec `--enable-libass` (par exemple via le tap `homebrew-ffmpeg/ffmpeg` avec l'option `--with-libass`, ou un build statique). Le chemin overlay donne un rendu équivalent sans rien installer.

La police des sous-titres est configurable via `FONT_PATH` et `CAPTION_FONT_SIZE` (défaut : Arial Bold, taille 76).

## Recadrage conscient du contenu

Le recadrage 9:16 n'est pas seulement centré visage (cas conférence). Chaque scène choisit sa stratégie (mode `auto` par défaut, ou forcé via `REFRAME_MODE` / `--reframe` / le sélecteur de l'UI) :

- **`face`** : talking-head, interview, vlog. Suit le visage dominant via **MediaPipe Tasks** (`blaze_face_short_range.tflite` téléchargé une fois dans `cache/models/`, fallback **OpenCV Haar** hors-ligne). Rappel vers le centre quand le visage est petit, gardes contre les foules (nombre de visages) et les spectateurs de premier rang (position basse).
- **`motion`** : sport, action, gameplay. Suit le **centroïde du mouvement** (différence de frames), pas un visage. C'est ce que choisit l'auto sur une vidéo de foot : le recadrage suit l'action.
- **`center`** : repli neutre.

Le recadrage est **lissé dans le temps** (pan fluide) : échantillonnage dense, moyenne glissante et bornage de la vitesse, interpolation linéaire au sein d'une scène et palier (saut) aux coupures.

Limite connue (phase 2, active speaker tracking audio) : un plan large où l'orateur est petit et sur le côté avec un spectateur proche de la caméra peut cadrer le spectateur. Forcer `--reframe center` ou `motion` contourne le cas.

## Optimisation de vitesse (M4)

- **Encodage** : déjà accéléré matériellement via `h264_videotoolbox`.
- **Transcription** : `faster-whisper` tourne sur CPU (CTranslate2, pas de CUDA). Pour aller plus vite sur Apple Silicon, le chemin d'optimisation est **`whisper.cpp` compilé avec le backend Metal**, qui exploite le GPU intégré. Ce n'est pas implémenté au MVP : la marche à suivre serait de remplacer l'appel `faster-whisper` dans `transcribe.py` par un appel au binaire `whisper-cli` de whisper.cpp (avec `--output-json` pour récupérer les timestamps mot à mot), en gardant la même structure `Transcript`.
- **Fonctionnement hors-ligne** : une fois les modèles Whisper et le modèle de détection de visage téléchargés, tout tourne hors-ligne (sauf l'étape `download` yt-dlp, qui nécessite le réseau).

## Phase 2 (non implémentée, stubs avec TODO)

- **Active speaker tracking** dans `reframe.py` : croiser l'activité audio et la position du visage, avec un pan panoramique fluide entre les frames au lieu d'un crop fixe par scène.
- **Provider `anthropic.py`** : appel à l'API Messages d'Anthropic (squelette présent).
- **API FastAPI** : exposer `POST /process {url}` et `GET /clips`.
- **Front Next.js** : interface web pour lancer un traitement, suivre la progression et prévisualiser les clips, consommant l'API FastAPI ci-dessus.

## Architecture du code

```
src/clipper/
  cli.py            # point d'entrée : clipper <url>
  config.py         # lecture .env, valeurs par défaut
  pipeline.py       # orchestration des étapes
  download.py       # yt-dlp
  transcribe.py     # faster-whisper, timestamps mot à mot
  segment.py        # sélection LLM (pluggable) + fallback heuristique
  reframe.py        # mediapipe + scenedetect -> crop 9:16
  captions.py       # génération ASS karaoké
  render.py         # ffmpeg cut + crop + burn + encode
  providers/
    base.py         # interface LLMProvider
    local_llm.py    # endpoint OpenAI-compatible (défaut)
    anthropic.py    # stub, phase 2
```
