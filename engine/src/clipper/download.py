"""Etape 1 : telechargement de la video source via yt-dlp.

Recupere un mp4 (<=1080p) dans le cache local et renvoie ses metadonnees.
Le fichier est mis en cache par id : un second appel sur la meme URL ne
re-telecharge pas.
"""

from __future__ import annotations

import logging
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

import yt_dlp

logger = logging.getLogger("clipper.download")

# Callback de progression du telechargement : (fraction 0..1, detail) -> None.
DownloadProgressFn = Callable[[float, dict], None]


@dataclass
class SourceVideo:
    path: Path
    video_id: str
    title: str
    url: str
    duration: float  # secondes


def _make_hook(on_progress: DownloadProgressFn):
    """Adapte les hooks yt-dlp (appeles tres souvent) en evenements throttled."""
    last = {"t": 0.0}

    def hook(d: dict) -> None:
        status = d.get("status")
        if status == "downloading":
            now = time.monotonic()
            if now - last["t"] < 0.25:  # throttle : ~4 maj/s max
                return
            last["t"] = now
            total = d.get("total_bytes") or d.get("total_bytes_estimate") or 0
            done = d.get("downloaded_bytes") or 0
            frac = (done / total) if total else 0.0
            on_progress(frac, {
                "kind": "download",
                "downloaded": int(done),
                "total": int(total),
                "speed": float(d.get("speed") or 0.0),
                "eta": int(d.get("eta") or 0),
            })
        elif status == "finished":
            done = int(d.get("downloaded_bytes") or 0)
            on_progress(1.0, {"kind": "download", "downloaded": done, "total": done, "speed": 0.0, "eta": 0})

    return hook


def download(url: str, cache_dir: Path, *, on_progress: DownloadProgressFn | None = None) -> SourceVideo:
    cache_dir.mkdir(parents=True, exist_ok=True)
    outtmpl = str(cache_dir / "%(id)s.%(ext)s")

    ydl_opts = {
        # Privilegie un mp4 H.264 <=1080p, fusionne video+audio en mp4.
        "format": "bv*[height<=1080][ext=mp4]+ba[ext=m4a]/b[height<=1080][ext=mp4]/b",
        "outtmpl": outtmpl,
        "merge_output_format": "mp4",
        "noplaylist": True,
        "quiet": True,
        "no_warnings": True,
        "retries": 3,
    }
    if on_progress is not None:
        ydl_opts["progress_hooks"] = [_make_hook(on_progress)]

    logger.info("Telechargement : %s", url)
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=True)
        if info is None:
            raise RuntimeError(f"yt-dlp n'a renvoye aucune info pour {url}")

        video_id = info["id"]
        # Chemin final apres fusion : yt-dlp force l'extension mp4.
        path = cache_dir / f"{video_id}.mp4"
        if not path.exists():
            # Replis : utiliser le nom prepare puis chercher un mp4 voisin.
            guess = Path(ydl.prepare_filename(info)).with_suffix(".mp4")
            if guess.exists():
                path = guess
            else:
                candidates = sorted(cache_dir.glob(f"{video_id}.*"))
                if not candidates:
                    raise FileNotFoundError(
                        f"Fichier telecharge introuvable pour {video_id} dans {cache_dir}"
                    )
                path = candidates[0]

    src = SourceVideo(
        path=path,
        video_id=video_id,
        title=info.get("title") or video_id,
        url=info.get("webpage_url") or url,
        duration=float(info.get("duration") or 0.0),
    )
    logger.info("Video prete : %s (%.0fs) -> %s", src.title, src.duration, src.path.name)
    return src
