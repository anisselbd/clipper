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


def _path_expr(keys, axis: str) -> str:
    """Expression ffmpeg du chemin de recadrage : interpolation lineaire (pan
    fluide) au sein d'une scene, palier (saut) aux coupures de scene.

    Les virgules internes sont echappees (\\,) pour ne pas etre prises pour des
    separateurs de filtre. Les parentheses et operateurs arithmetiques sont
    litteraux dans un filtergraph.
    """
    def val(k):
        return int(round(k.x if axis == "x" else k.y))

    pts = [(k.t, val(k), k.scene) for k in keys]
    expr = str(pts[-1][1])
    for i in range(len(pts) - 2, -1, -1):
        t0, v0, sc0 = pts[i]
        t1, v1, sc1 = pts[i + 1]
        if sc0 != sc1 or (t1 - t0) < 0.05:
            seg = str(v0)  # coupe ou segment quasi nul -> palier
        else:
            seg = f"({v0}+({v1 - v0})*(t-{t0:.3f})/{t1 - t0:.3f})"
        expr = f"if(lt(t\\,{t1:.3f})\\,{seg}\\,{expr})"
    return expr


def build_crop_filter(plan: ReframePlan) -> str:
    """Genere le filtre crop (constant si fixe, sinon chemin interpole)."""
    w, h = plan.crop_w, plan.crop_h
    keys = plan.keys or []
    if not keys:
        return f"crop={w}:{h}:0:0"

    if plan.axis == "x":
        const_y = keys[0].y
        if len(keys) == 1 or len({k.x for k in keys}) == 1:
            return f"crop={w}:{h}:{keys[0].x}:{const_y}"
        return f"crop={w}:{h}:{_path_expr(keys, 'x')}:{const_y}"
    else:
        const_x = keys[0].x
        if len(keys) == 1 or len({k.y for k in keys}) == 1:
            return f"crop={w}:{h}:{const_x}:{keys[0].y}"
        return f"crop={w}:{h}:{const_x}:{_path_expr(keys, 'y')}"


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
