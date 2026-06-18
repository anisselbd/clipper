"""Etape 7 : rendu final ffmpeg.

Un appel ffmpeg par clip : decoupe (-ss/-t), crop calcule par reframe, scale
1080x1920, incrustation des sous-titres ASS, encodage materiel
h264_videotoolbox. Le `t` des expressions de crop et les timestamps de l'ASS
sont clip-locaux (l'amorce d'entree remet les PTS a ~0).
"""

from __future__ import annotations

import functools
import logging
import subprocess
from pathlib import Path

from .reframe import ReframePlan

logger = logging.getLogger("clipper.render")


@functools.lru_cache(maxsize=1)
def subtitles_backend() -> str:
    """Detecte si ffmpeg embarque libass ('libass') sinon overlay Pillow ('overlay')."""
    try:
        out = subprocess.run(
            ["ffmpeg", "-hide_banner", "-filters"], capture_output=True, text=True
        ).stdout
    except Exception:
        return "overlay"
    for line in out.splitlines():
        parts = line.split()
        if len(parts) >= 2 and parts[1] in ("ass", "subtitles"):
            return "libass"
    return "overlay"


def _encode_args(encoder: str, bitrate: str, fps: int) -> list[str]:
    return [
        "-r", str(fps),
        "-c:v", encoder,
        "-b:v", bitrate,
        "-allow_sw", "1",
        "-pix_fmt", "yuv420p",
        "-c:a", "aac",
        "-b:a", "160k",
        "-ar", "48000",
        "-movflags", "+faststart",
    ]


def _step_expr(triples: list[tuple[float, float, int]]) -> str:
    """Construit une expression ffmpeg en escalier : valeur par plage temporelle.

    triples = [(t0, t1, valeur), ...] (clip-locaux). Les virgules internes sont
    echappees (\\,) pour ne pas etre prises pour des separateurs de filtre.
    """
    expr = str(triples[-1][2])
    for t0, t1, val in reversed(triples[:-1]):
        expr = f"if(between(t\\,{t0:.3f}\\,{t1:.3f})\\,{val}\\,{expr})"
    return expr


def build_crop_filter(plan: ReframePlan) -> str:
    """Genere le filtre crop (constant si une scene, sinon expression temporelle)."""
    w, h = plan.crop_w, plan.crop_h
    scenes = plan.scenes or []
    if not scenes:
        return f"crop={w}:{h}:0:0"

    if plan.axis == "x":
        values = [sc.x for sc in scenes]
        const_y = scenes[0].y
        if len(scenes) == 1 or len(set(values)) == 1:
            return f"crop={w}:{h}:{values[0]}:{const_y}"
        expr = _step_expr([(sc.t0, sc.t1, sc.x) for sc in scenes])
        return f"crop={w}:{h}:{expr}:{const_y}"
    else:
        values = [sc.y for sc in scenes]
        const_x = scenes[0].x
        if len(scenes) == 1 or len(set(values)) == 1:
            return f"crop={w}:{h}:{const_x}:{values[0]}"
        expr = _step_expr([(sc.t0, sc.t1, sc.y) for sc in scenes])
        return f"crop={w}:{h}:{const_x}:{expr}"


def build_filtergraph(plan: ReframePlan, ass_name: str, target_w: int, target_h: int) -> str:
    crop = build_crop_filter(plan)
    return (
        f"{crop},"
        f"scale={target_w}:{target_h}:flags=lanczos,"
        f"setsar=1,"
        f"ass={ass_name}"
    )


def render_clip(
    source: Path,
    start: float,
    end: float,
    plan: ReframePlan,
    ass_path: Path,
    out_path: Path,
    *,
    target_w: int = 1080,
    target_h: int = 1920,
    fps: int = 30,
    encoder: str = "h264_videotoolbox",
    bitrate: str = "8M",
) -> Path:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    duration = max(0.1, end - start)
    # On execute avec cwd = dossier de sortie pour referencer l'ASS sans
    # echappement de chemin delicat dans le filtergraph.
    workdir = out_path.parent
    ass_name = ass_path.name
    filtergraph = build_filtergraph(plan, ass_name, target_w, target_h)

    cmd = [
        "ffmpeg", "-y",
        "-ss", f"{start:.3f}",
        "-i", str(source.resolve()),
        "-t", f"{duration:.3f}",
        "-vf", filtergraph,
        *_encode_args(encoder, bitrate, fps),
        out_path.name,
    ]

    logger.info("Rendu (libass) : %s (%.1fs)", out_path.name, duration)
    proc = subprocess.run(cmd, cwd=str(workdir), capture_output=True, text=True)
    if proc.returncode != 0:
        raise RuntimeError(
            f"ffmpeg a echoue pour {out_path.name}:\n{proc.stderr[-2500:]}"
        )
    if not out_path.exists() or out_path.stat().st_size == 0:
        raise RuntimeError(f"Sortie vide pour {out_path}")
    return out_path


def render_clip_overlay(
    source: Path,
    start: float,
    end: float,
    plan: ReframePlan,
    concat_list: Path | None,
    out_path: Path,
    *,
    target_w: int = 1080,
    target_h: int = 1920,
    fps: int = 30,
    encoder: str = "h264_videotoolbox",
    bitrate: str = "8M",
) -> Path:
    """Rendu sans libass : crop + scale + incrustation des sous-titres via overlay PNG."""
    out_path.parent.mkdir(parents=True, exist_ok=True)
    duration = max(0.1, end - start)
    crop = build_crop_filter(plan)

    cmd = [
        "ffmpeg", "-y",
        "-ss", f"{start:.3f}",
        "-t", f"{duration:.3f}",
        "-i", str(source.resolve()),
    ]
    if concat_list is not None:
        cmd += ["-f", "concat", "-safe", "0", "-i", str(concat_list.resolve())]
        filter_complex = (
            f"[0:v]{crop},scale={target_w}:{target_h}:flags=lanczos,setsar=1[base];"
            f"[1:v]format=rgba,scale={target_w}:{target_h}[ov];"
            f"[base][ov]overlay=0:0:shortest=1,format=yuv420p[v]"
        )
    else:
        filter_complex = (
            f"[0:v]{crop},scale={target_w}:{target_h}:flags=lanczos,setsar=1,"
            f"format=yuv420p[v]"
        )

    cmd += [
        "-filter_complex", filter_complex,
        "-map", "[v]",
        "-map", "0:a?",
        *_encode_args(encoder, bitrate, fps),
        str(out_path.resolve()),
    ]

    logger.info("Rendu (overlay) : %s (%.1fs)", out_path.name, duration)
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        raise RuntimeError(
            f"ffmpeg a echoue pour {out_path.name}:\n{proc.stderr[-2500:]}"
        )
    if not out_path.exists() or out_path.stat().st_size == 0:
        raise RuntimeError(f"Sortie vide pour {out_path}")
    return out_path


def probe_resolution(path: Path) -> tuple[int, int] | None:
    """Renvoie (largeur, hauteur) via ffprobe, ou None."""
    cmd = [
        "ffprobe", "-v", "error",
        "-select_streams", "v:0",
        "-show_entries", "stream=width,height",
        "-of", "csv=p=0:s=x",
        str(path),
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        return None
    try:
        w, h = proc.stdout.strip().split("x")
        return int(w), int(h)
    except ValueError:
        return None
