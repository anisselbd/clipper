"""Etape 0 : preflight environnement.

Lecon n.1 du RETEX : ne jamais supposer une capacite externe, la verifier.
Ce module sonde la machine et produit un rapport (PreflightReport) a partir
duquel le reste du code choisit ses chemins (encodeur, backend sous-titres,
detecteur de visage, selection LLM ou heuristique). Aucun chemin n'est code en
dur ni choisi par config manuelle.
"""

from __future__ import annotations

import logging
import platform
import subprocess
import sys
from dataclasses import asdict, dataclass, field

logger = logging.getLogger("clipper.preflight")


@dataclass
class PreflightReport:
    python_version: str
    python_ok: bool

    ffmpeg_present: bool
    ffmpeg_version: str
    has_libass: bool
    has_drawtext: bool
    subtitle_backend: str  # "libass" | "overlay"

    has_videotoolbox: bool
    has_libx264: bool
    video_encoder: str  # encodeur retenu

    face_backend: str  # "mediapipe" | "haar"

    llm_base_url: str
    llm_reachable: bool
    selection_backend: str  # "llm" | "heuristic"

    warnings: list[str] = field(default_factory=list)

    def as_dict(self) -> dict:
        return asdict(self)

    def log(self) -> None:
        logger.info("Preflight :")
        logger.info("  python           : %s (%s)", self.python_version, "ok" if self.python_ok else "ATTENTION <3.12")
        logger.info("  ffmpeg           : %s", self.ffmpeg_version or "ABSENT")
        logger.info("  sous-titres      : %s (libass=%s, drawtext=%s)", self.subtitle_backend, self.has_libass, self.has_drawtext)
        logger.info("  encodeur video   : %s (videotoolbox=%s, libx264=%s)", self.video_encoder, self.has_videotoolbox, self.has_libx264)
        logger.info("  detection visage : %s", self.face_backend)
        logger.info("  selection        : %s (llm joignable=%s sur %s)", self.selection_backend, self.llm_reachable, self.llm_base_url)
        for w in self.warnings:
            logger.warning("  ! %s", w)


# --------------------------------------------------------------------------- #
# Sondes individuelles
# --------------------------------------------------------------------------- #

def _ffmpeg_lists() -> tuple[bool, str, set[str], set[str]]:
    """Renvoie (present, version, filtres, encodeurs) de ffmpeg."""
    try:
        ver = subprocess.run(["ffmpeg", "-hide_banner", "-version"], capture_output=True, text=True)
        version = ver.stdout.splitlines()[0] if ver.stdout else ""
        filt = subprocess.run(["ffmpeg", "-hide_banner", "-filters"], capture_output=True, text=True).stdout
        enc = subprocess.run(["ffmpeg", "-hide_banner", "-encoders"], capture_output=True, text=True).stdout
    except (FileNotFoundError, OSError):
        return False, "", set(), set()

    filters = set()
    for line in filt.splitlines():
        parts = line.split()
        if len(parts) >= 2:
            filters.add(parts[1])
    encoders = set()
    for line in enc.splitlines():
        parts = line.split()
        if len(parts) >= 2:
            encoders.add(parts[1])
    return True, version, filters, encoders


def _mediapipe_tasks_ok() -> bool:
    try:
        from mediapipe.tasks.python import vision  # noqa: F401

        return True
    except Exception:
        return False


def _llm_reachable(base_url: str, timeout: float = 3.0) -> bool:
    try:
        import httpx

        r = httpx.get(f"{base_url.rstrip('/')}/models", timeout=timeout)
        return r.status_code < 500
    except Exception:
        return False


# --------------------------------------------------------------------------- #
# Rapport
# --------------------------------------------------------------------------- #

def run_preflight(config) -> PreflightReport:
    warnings: list[str] = []

    py = platform.python_version()
    python_ok = sys.version_info[:2] == (3, 12)
    if not python_ok:
        warnings.append(f"Python {py} : le moteur cible 3.12 (deps ML).")

    present, version, filters, encoders = _ffmpeg_lists()
    if not present:
        warnings.append("ffmpeg introuvable dans le PATH.")

    has_libass = "ass" in filters or "subtitles" in filters
    has_drawtext = "drawtext" in filters
    subtitle_backend = "libass" if has_libass else "overlay"
    if not has_libass:
        warnings.append("ffmpeg sans libass : incrustation des sous-titres par overlay PNG (Pillow).")

    has_vt = "h264_videotoolbox" in encoders
    has_x264 = "libx264" in encoders
    if has_vt:
        video_encoder = "h264_videotoolbox"
    elif has_x264:
        video_encoder = "libx264"
    else:
        video_encoder = "libx264"  # dernier recours, ffmpeg le construit souvent en interne
        warnings.append("Ni videotoolbox ni libx264 detectes : tentative libx264 par defaut.")

    face_backend = "mediapipe" if _mediapipe_tasks_ok() else "haar"
    if face_backend == "haar":
        warnings.append("MediaPipe Tasks indisponible : fallback OpenCV Haar.")

    base_url = config.llm_base_url
    reachable = _llm_reachable(base_url, timeout=getattr(config, "preflight_llm_timeout", 3.0))
    selection_backend = "llm" if reachable else "heuristic"
    if not reachable:
        warnings.append(f"llama-server injoignable sur {base_url} : selection heuristique (local-first).")

    report = PreflightReport(
        python_version=py,
        python_ok=python_ok,
        ffmpeg_present=present,
        ffmpeg_version=version,
        has_libass=has_libass,
        has_drawtext=has_drawtext,
        subtitle_backend=subtitle_backend,
        has_videotoolbox=has_vt,
        has_libx264=has_x264,
        video_encoder=video_encoder,
        face_backend=face_backend,
        llm_base_url=base_url,
        llm_reachable=reachable,
        selection_backend=selection_backend,
        warnings=warnings,
    )
    return report
