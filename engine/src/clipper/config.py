"""Configuration centrale : lecture du .env et valeurs par defaut.

Toutes les options sont surchargeables par variable d'environnement (ou .env).
Aucune cle API n'est requise dans la configuration par defaut (LLM local).
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv

# Charge un eventuel .env present dans le repertoire courant, sans ecraser
# les variables deja definies dans l'environnement.
load_dotenv(override=False)


def _env_bool(name: str, default: bool) -> bool:
    val = os.getenv(name)
    if val is None:
        return default
    return val.strip().lower() not in ("0", "false", "no", "off", "")


@dataclass
class Config:
    """Parametres du pipeline, resolus depuis l'environnement a la creation."""

    # --- LLM (selection des moments forts) ---
    llm_provider: str = field(default_factory=lambda: os.getenv("LLM_PROVIDER", "local_llm"))
    llm_base_url: str = field(default_factory=lambda: os.getenv("LLM_BASE_URL", "http://localhost:8080/v1"))
    llm_model: str = field(default_factory=lambda: os.getenv("LLM_MODEL", "qwen3"))
    llm_api_key: str | None = field(default_factory=lambda: os.getenv("LLM_API_KEY") or None)
    llm_timeout: float = field(default_factory=lambda: float(os.getenv("LLM_TIMEOUT", "180")))
    # Desactive le mode "thinking" (Qwen3 et co.) : selection plus rapide, JSON
    # direct. Sans effet sur les modeles dont le template l'ignore.
    llm_disable_thinking: bool = field(default_factory=lambda: _env_bool("LLM_DISABLE_THINKING", True))
    # Reessais par fenetre si la reponse n'est pas un JSON exploitable.
    llm_retries: int = field(default_factory=lambda: int(os.getenv("LLM_RETRIES", "2")))
    # Sortie structuree (RETEX) : response_format json_schema cote serveur.
    llm_structured_output: bool = field(default_factory=lambda: _env_bool("LLM_STRUCTURED_OUTPUT", True))
    preflight_llm_timeout: float = field(default_factory=lambda: float(os.getenv("PREFLIGHT_LLM_TIMEOUT", "3")))

    # --- Transcription (faster-whisper) ---
    whisper_model: str = field(default_factory=lambda: os.getenv("WHISPER_MODEL", "small"))
    whisper_device: str = field(default_factory=lambda: os.getenv("WHISPER_DEVICE", "cpu"))
    whisper_compute_type: str = field(default_factory=lambda: os.getenv("WHISPER_COMPUTE_TYPE", "int8"))
    lang: str = field(default_factory=lambda: os.getenv("LANG_CODE", "fr"))

    # --- Selection des segments ---
    clips: int = field(default_factory=lambda: int(os.getenv("CLIPS", "8")))
    min_duration: float = field(default_factory=lambda: float(os.getenv("MIN_DURATION", "20")))
    max_duration: float = field(default_factory=lambda: float(os.getenv("MAX_DURATION", "60")))
    # Detecte les reactions sonores fortes (temps forts sport) en indice de selection.
    audio_highlights: bool = field(default_factory=lambda: _env_bool("AUDIO_HIGHLIGHTS", True))

    # --- Recadrage ---
    # auto (decision par scene), face, motion, center.
    reframe_mode: str = field(default_factory=lambda: os.getenv("REFRAME_MODE", "auto"))
    per_scene_reframe: bool = field(default_factory=lambda: _env_bool("PER_SCENE_REFRAME", True))
    scene_threshold: float = field(default_factory=lambda: float(os.getenv("SCENE_THRESHOLD", "27")))
    face_confidence: float = field(default_factory=lambda: float(os.getenv("FACE_CONFIDENCE", "0.5")))
    samples_per_scene: int = field(default_factory=lambda: int(os.getenv("SAMPLES_PER_SCENE", "5")))

    # --- Rendu video ---
    target_w: int = 1080
    target_h: int = 1920
    fps: int = field(default_factory=lambda: int(os.getenv("FPS", "30")))
    video_encoder: str = field(default_factory=lambda: os.getenv("VIDEO_ENCODER", "h264_videotoolbox"))
    video_bitrate: str = field(default_factory=lambda: os.getenv("VIDEO_BITRATE", "8M"))

    # --- Sous-titres ---
    caption_font: str | None = field(default_factory=lambda: os.getenv("FONT_PATH") or None)
    caption_font_size: int = field(default_factory=lambda: int(os.getenv("CAPTION_FONT_SIZE", "76")))

    # --- API / serveur ---
    api_host: str = field(default_factory=lambda: os.getenv("API_HOST", "127.0.0.1"))
    api_port: int = field(default_factory=lambda: int(os.getenv("API_PORT", "8008")))
    public_base_url: str = field(default_factory=lambda: os.getenv("PUBLIC_BASE_URL", "http://localhost:8008"))
    worker_concurrency: int = field(default_factory=lambda: int(os.getenv("WORKER_CONCURRENCY", "1")))

    # --- Chemins ---
    output_dir: Path = field(default_factory=lambda: Path(os.getenv("OUTPUT_DIR", "output")))
    cache_dir: Path = field(default_factory=lambda: Path(os.getenv("CACHE_DIR", "cache")))
    data_dir: Path = field(default_factory=lambda: Path(os.getenv("DATA_DIR", "data")))

    def ensure_dirs(self) -> None:
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        (self.cache_dir / "models").mkdir(parents=True, exist_ok=True)

    @property
    def models_dir(self) -> Path:
        return self.cache_dir / "models"

    @property
    def db_path(self) -> Path:
        return self.data_dir / "clipper.db"
