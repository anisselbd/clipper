"""Detection des incrustations de diffuseur (logo de chaine) pour les masquer.

Probleme : sur un flux TV (foot, etc.), le logo de chaine (M6, TF1, beIN...) est
incruste dans l'image. Pour de la republication, on veut l'effacer. Le bandeau
score, lui, donne du contexte : on le GARDE.

Methode, agnostique a la chaine : un logo reste FIXE a l'ecran pendant que le
terrain bouge -> il a une variance temporelle faible la ou le reste varie. On
calcule la carte de variance sur un echantillon d'images, on garde les zones
statiques des coins HAUT, et on distingue le logo (compact) du bandeau score
(large) par la largeur du bloc. On renvoie des rectangles a passer au filtre
ffmpeg `delogo`, qui reconstruit la zone a partir des pixels autour.
"""

from __future__ import annotations

import logging

logger = logging.getLogger("clipper.overlays")


def _merge_overlapping(boxes: list[tuple[int, int, int, int]]) -> list[tuple[int, int, int, int]]:
    """Fusionne les rectangles qui se recouvrent (union des bornes)."""
    boxes = list(boxes)
    merged = True
    while merged:
        merged = False
        out: list[tuple[int, int, int, int]] = []
        while boxes:
            x, y, w, h = boxes.pop()
            x2, y2 = x + w, y + h
            i = 0
            while i < len(out):
                ox, oy, ow, oh = out[i]
                if not (x2 < ox or ox + ow < x or y2 < oy or oy + oh < y):
                    nx, ny = min(x, ox), min(y, oy)
                    x, y = nx, ny
                    x2, y2 = max(x2, ox + ow), max(y2, oy + oh)
                    w, h = x2 - x, y2 - y
                    out.pop(i)
                    merged = True
                else:
                    i += 1
            out.append((x, y, w, h))
        boxes = out
    return boxes


def detect_logo_regions(
    video_path,
    *,
    samples: int = 36,
    dscale_w: int = 480,
) -> list[tuple[int, int, int, int]]:
    """Renvoie les rectangles (x, y, w, h) du/des logo(s) de chaine, en pixels
    source. Liste vide si rien de fiable (camera fixe, pas de logo, talking-head).
    """
    try:
        import cv2
        import numpy as np
    except Exception:
        return []

    cap = cv2.VideoCapture(str(video_path))
    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    nfr = cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0
    src_w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    src_h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    if nfr <= 0 or src_w <= 0 or src_h <= 0:
        cap.release()
        return []
    dur = nfr / fps
    W = dscale_w
    H = max(1, int(round(W * src_h / src_w)))

    frames = []
    for f in np.linspace(0.12, 0.92, samples):
        cap.set(cv2.CAP_PROP_POS_MSEC, float(f) * dur * 1000.0)
        ok, fr = cap.read()
        if ok and fr is not None:
            frames.append(cv2.cvtColor(cv2.resize(fr, (W, H)), cv2.COLOR_BGR2GRAY).astype(np.float32))
    cap.release()
    if len(frames) < 8:
        return []

    std = np.stack(frames).std(axis=0)
    # Camera quasi-fixe : tout est statique, la discrimination n'a pas de sens.
    if float(np.median(std)) < 6.0:
        logger.info("Detection logo : scene trop statique, ignoree.")
        return []

    # Seuil ABSOLU bas : un vrai logo ne change JAMAIS (variance ~ 0). Les
    # tribunes/joueurs varient beaucoup, et meme le bandeau score varie (horloge
    # qui tourne) -> il n'est PAS capture, donc garde. C'est ce qu'on veut.
    thr = 10.0
    static = (std < thr).astype(np.uint8)

    # Les logos vivent dans les bandes HAUT/BAS (coins), jamais au centre.
    band = np.zeros_like(static)
    band[: int(H * 0.24), :] = 1
    band[int(H * 0.80) :, :] = 1
    static = static * band

    # Fermeture modeste : ressoude un logo et son texte ("DIRECT") sous lui.
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (25, 11))
    static = cv2.morphologyEx(static, cv2.MORPH_CLOSE, kernel)

    cnts, _ = cv2.findContours(static, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    sx, sy = src_w / W, src_h / H
    regions: list[tuple[int, int, int, int]] = []
    for c in cnts:
        x, y, w, h = cv2.boundingRect(c)
        X, Y, Wd, Hd = x * sx, y * sy, w * sx, h * sy
        cx = X + Wd / 2.0
        area_frac = (Wd * Hd) / (src_w * src_h)
        compact = Wd < src_w * 0.18 and Hd < src_h * 0.20
        corner = cx < src_w * 0.25 or cx > src_w * 0.75
        # Bloc large = bandeau score -> on le garde (skip). Trop petit = bruit.
        if not (compact and corner and 0.0006 < area_frac < 0.03):
            continue
        # Marge autour + clamp pour ne pas toucher les bords (delogo l'exige).
        mx, my = int(Wd * 0.22) + 10, int(Hd * 0.30) + 12
        rx, ry = max(1, int(X) - mx), max(1, int(Y) - my)
        rw = min(int(Wd) + 2 * mx, src_w - 2 - rx)
        rh = min(int(Hd) + 2 * my, src_h - 2 - ry)
        if rw > 4 and rh > 4:
            regions.append((rx, ry, rw, rh))

    regions = _merge_overlapping(regions)
    if regions:
        logger.info("Logo(s) de chaine detecte(s) : %s", regions)
    else:
        logger.info("Aucun logo de chaine detecte.")
    return regions


def build_delogo_chain(regions: list[tuple[int, int, int, int]]) -> str:
    """Construit la chaine de filtres ffmpeg `delogo` pour les regions donnees.

    Renvoie une chaine vide si aucune region.
    """
    return ",".join(f"delogo=x={x}:y={y}:w={w}:h={h}" for (x, y, w, h) in regions)
