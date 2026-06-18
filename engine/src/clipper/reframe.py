"""Etape 5 : recadrage 16:9 -> 9:16 conscient du contenu.

Le recadrage n'est plus seulement centre sur un visage (cas conference). Selon
le contenu, chaque scene choisit sa strategie :

- "face"   : talking-head, interview, vlog -> suit le visage dominant (MediaPipe
             Tasks, fallback OpenCV Haar).
- "motion" : sport, action, gameplay -> suit l'action via flot optique avec
             compensation du panoramique camera (on retire le balayage et on
             vise le mouvement residuel des joueurs/ballon). Pan rapide.
- "center" : repli (rien d'exploitable).

Mode special "fullwidth" : pas de crop du tout. Le rendu garde TOUTE la largeur
de la source dans une bande centrale, haut et bas remplis d'un zoom flou (cf.
render.render_clip_fullwidth). Rien ne sort du cadre horizontalement : pour le
sport en plan large ou un crop 9:16 ne peut pas contenir le tireur ET le but.

Le mode est "auto" par defaut (decision par scene) ou force (face/motion/center/fullwidth).
Le recadrage est lisse dans le temps (pan fluide) plutot qu'un crop fige par
scene : moyenne glissante + bornage de la vitesse + rappel vers le centre.

TODO phase 2+ : active speaker tracking (croiser piste audio et visages quand
plusieurs personnes parlent), detection d'objet (ballon) pour le sport.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path

logger = logging.getLogger("clipper.reframe")

FACE_MODEL_URL = (
    "https://storage.googleapis.com/mediapipe-models/face_detector/"
    "blaze_face_short_range/float16/1/blaze_face_short_range.tflite"
)
FACE_MODEL_NAME = "blaze_face_short_range.tflite"


@dataclass
class CropKey:
    """Point cle du chemin de recadrage. Temps RELATIF au clip (secondes)."""

    t: float
    x: int
    y: int
    scene: int  # index de scene : un changement de scene = coupe (saut, pas pan)


@dataclass
class ReframePlan:
    src_w: int
    src_h: int
    crop_w: int
    crop_h: int
    axis: str  # "x" (pan horizontal) ou "y" (vertical)
    keys: list[CropKey] = field(default_factory=list)
    strategy: str = "center"
    n_scenes: int = 1
    layout: str = "crop"  # "crop" (cadre suiveur) ou "fullwidth" (bandes floues)


# --------------------------------------------------------------------------- #
# Geometrie du crop (testable sans dependances lourdes)
# --------------------------------------------------------------------------- #

def compute_crop_window(src_w: int, src_h: int, ratio_w: int = 9, ratio_h: int = 16) -> tuple[int, int, str]:
    target = ratio_w / ratio_h
    source = src_w / src_h
    if source >= target:
        crop_h = src_h
        crop_w = int(round(src_h * target))
        axis = "x"
    else:
        crop_w = src_w
        crop_h = int(round(src_w / target))
        axis = "y"
    crop_w = min(src_w, crop_w - (crop_w % 2))
    crop_h = min(src_h, crop_h - (crop_h % 2))
    return crop_w, crop_h, axis


def clamp_origin(center: float, crop_size: int, src_size: int) -> int:
    origin = int(round(center - crop_size / 2))
    return max(0, min(origin, src_size - crop_size))


def smooth_series(values: list[float], win: int = 5, max_step: float | None = None) -> list[float]:
    """Moyenne glissante + bornage de la vitesse (pan fluide, sans a-coups)."""
    if not values:
        return values
    half = max(0, win // 2)
    out: list[float] = []
    for i in range(len(values)):
        lo, hi = max(0, i - half), min(len(values), i + half + 1)
        out.append(sum(values[lo:hi]) / (hi - lo))
    if max_step is not None:
        for i in range(1, len(out)):
            delta = out[i] - out[i - 1]
            if delta > max_step:
                out[i] = out[i - 1] + max_step
            elif delta < -max_step:
                out[i] = out[i - 1] - max_step
    return out


# --------------------------------------------------------------------------- #
# Detection de visage (MediaPipe Tasks, fallback Haar OpenCV)
# --------------------------------------------------------------------------- #

def ensure_face_model(models_dir: Path) -> Path | None:
    models_dir.mkdir(parents=True, exist_ok=True)
    path = models_dir / FACE_MODEL_NAME
    if path.exists() and path.stat().st_size > 0:
        return path
    try:
        import httpx

        logger.info("Telechargement du modele de detection de visage (une fois)...")
        with httpx.stream("GET", FACE_MODEL_URL, timeout=60.0, follow_redirects=True) as r:
            r.raise_for_status()
            with open(path, "wb") as fh:
                for chunk in r.iter_bytes():
                    fh.write(chunk)
        return path
    except Exception as exc:
        logger.warning("Modele MediaPipe indisponible (%s). Fallback OpenCV Haar.", exc)
        if path.exists():
            path.unlink(missing_ok=True)
        return None


class FaceDetector:
    """Detecteur unifie : MediaPipe Tasks si possible, sinon Haar OpenCV."""

    def __init__(self, models_dir: Path, min_confidence: float = 0.5) -> None:
        self.min_confidence = min_confidence
        self._mp = None
        self._haar = None
        model_path = ensure_face_model(models_dir)
        if model_path is not None:
            self._mp = self._try_load_mediapipe(model_path, min_confidence)
        if self._mp is None:
            self._haar = self._load_haar()
        self.backend = "mediapipe" if self._mp is not None else ("haar" if self._haar is not None else "none")
        logger.info("Detecteur de visage : %s", self.backend)

    @staticmethod
    def _try_load_mediapipe(model_path: Path, min_conf: float):
        try:
            from mediapipe.tasks import python as mpp
            from mediapipe.tasks.python import vision

            base = mpp.BaseOptions(model_asset_path=str(model_path))
            opts = vision.FaceDetectorOptions(base_options=base, min_detection_confidence=min_conf)
            return vision.FaceDetector.create_from_options(opts)
        except Exception as exc:
            logger.warning("Init MediaPipe FaceDetector echouee (%s).", exc)
            return None

    @staticmethod
    def _load_haar():
        try:
            import cv2

            path = cv2.data.haarcascades + "haarcascade_frontalface_default.xml"
            cascade = cv2.CascadeClassifier(path)
            return None if cascade.empty() else cascade
        except Exception as exc:
            logger.warning("Init Haar OpenCV echouee (%s).", exc)
            return None

    def detect_all(self, frame_bgr) -> list[tuple[float, float, float]]:
        """Tous les visages : liste de (cx, cy, aire) en pixels."""
        if self._mp is not None:
            return self._all_mediapipe(frame_bgr)
        if self._haar is not None:
            return self._all_haar(frame_bgr)
        return []

    def center(self, frame_bgr) -> tuple[float, float, float] | None:
        """Visage dominant (le plus grand), ou None."""
        faces = self.detect_all(frame_bgr)
        return max(faces, key=lambda f: f[2]) if faces else None

    def _all_mediapipe(self, frame_bgr):
        import cv2
        import mediapipe as mp

        rgb = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB)
        mp_img = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb)
        res = self._mp.detect(mp_img)
        out = []
        for det in res.detections:
            b = det.bounding_box
            out.append((b.origin_x + b.width / 2.0, b.origin_y + b.height / 2.0, float(b.width * b.height)))
        return out

    def _all_haar(self, frame_bgr):
        import cv2

        gray = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2GRAY)
        faces = self._haar.detectMultiScale(gray, scaleFactor=1.1, minNeighbors=5, minSize=(60, 60))
        return [(x + w / 2.0, y + h / 2.0, float(w * h)) for (x, y, w, h) in faces]


# --------------------------------------------------------------------------- #
# Detection de scenes
# --------------------------------------------------------------------------- #

def detect_scenes(video_path: Path, start: float, end: float, threshold: float) -> list[tuple[float, float]]:
    try:
        from scenedetect import ContentDetector, SceneManager, open_video

        video = open_video(str(video_path))
        sm = SceneManager()
        sm.add_detector(ContentDetector(threshold=threshold))
        video.seek(start)
        sm.detect_scenes(video=video, end_time=float(end))
        raw = sm.get_scene_list()
        scenes = []
        for s, e in raw:
            ss = max(start, s.get_seconds())
            ee = min(end, e.get_seconds())
            if ee - ss > 0.5:
                scenes.append((ss, ee))
        if scenes:
            return scenes
    except Exception as exc:
        logger.warning("Detection de scenes indisponible (%s). Scene unique.", exc)
    return [(start, end)]


# --------------------------------------------------------------------------- #
# Echantillonnage des centres : visage et mouvement
# --------------------------------------------------------------------------- #

def _video_dimensions(video_path: Path) -> tuple[int, int]:
    import cv2

    cap = cv2.VideoCapture(str(video_path))
    w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    cap.release()
    if w <= 0 or h <= 0:
        raise RuntimeError(f"Dimensions video illisibles pour {video_path}")
    return w, h


def _sample_times(t0: float, t1: float, dt: float) -> list[float]:
    n = max(1, int((t1 - t0) / dt))
    return [t0 + (t1 - t0) * (i + 0.5) / n for i in range(n)]


def _face_samples(cap, detector: FaceDetector, times: list[float]):
    """Par instant : centre du visage dominant (ou None), tailles rel, nb moyen
    de visages (pour distinguer un orateur d'une foule/public)."""
    import cv2

    out: list[tuple[float, float] | None] = []
    sizes: list[float] = []
    counts: list[int] = []
    W = cap.get(cv2.CAP_PROP_FRAME_WIDTH) or 1
    for t in times:
        cap.set(cv2.CAP_PROP_POS_MSEC, t * 1000.0)
        ok, frame = cap.read()
        if not ok or frame is None:
            out.append(None)
            continue
        faces = detector.detect_all(frame)
        counts.append(len(faces))
        if not faces:
            out.append(None)
            continue
        best = max(faces, key=lambda f: f[2])
        out.append((best[0], best[1]))
        sizes.append((best[2] ** 0.5) / W)
    avg_count = (sum(counts) / len(counts)) if counts else 0.0
    return out, sizes, avg_count


def _motion_samples(cap, times: list[float], src_w: int, src_h: int) -> list[tuple[float, float] | None]:
    """Centroide du mouvement (diff de frames) par instant, ou None si statique.

    Repli simple (utilise si le flot optique echoue). Ne distingue PAS le
    mouvement de la camera de celui des joueurs : se rabat au centre des qu'un
    panoramique fait tout bouger.
    """
    import cv2

    scale = 320.0 / src_w
    out: list[tuple[float, float] | None] = []
    for t in times:
        cap.set(cv2.CAP_PROP_POS_MSEC, t * 1000.0)
        ok1, f1 = cap.read()
        ok2, f2 = cap.read()
        if not (ok1 and ok2) or f1 is None or f2 is None:
            out.append(None)
            continue
        small1 = cv2.cvtColor(cv2.resize(f1, (0, 0), fx=scale, fy=scale), cv2.COLOR_BGR2GRAY)
        small2 = cv2.cvtColor(cv2.resize(f2, (0, 0), fx=scale, fy=scale), cv2.COLOR_BGR2GRAY)
        diff = cv2.absdiff(small1, small2)
        _, mask = cv2.threshold(diff, 18, 255, cv2.THRESH_BINARY)
        coverage = float(mask.mean()) / 255.0
        m = cv2.moments(mask, binaryImage=True)
        if m["m00"] < 1e-3 or coverage < 0.005:
            out.append(None)  # rien ne bouge -> on laissera le rappel au centre
            continue
        cx = (m["m10"] / m["m00"]) / scale
        cy = (m["m01"] / m["m00"]) / scale
        # Camera qui balaye (tout bouge) -> rappel vers le centre.
        if coverage > 0.45:
            cx = 0.5 * cx + 0.5 * (src_w / 2.0)
            cy = 0.5 * cy + 0.5 * (src_h / 2.0)
        out.append((cx, cy))
    return out


def _action_samples(cap, times: list[float], src_w: int, src_h: int) -> list[tuple[float, float] | None]:
    """Centre de l'ACTION par instant, robuste au panoramique camera (sport).

    Flot optique dense (Farneback) entre deux frames consecutives. On estime le
    mouvement GLOBAL de la camera (mediane du flot, robuste car les joueurs sont
    minoritaires en pixels) et on le retire : le mouvement RESIDUEL est celui des
    joueurs et du ballon, independamment du balayage. On vise le centroide de ce
    residu, pondere par sa magnitude et limite aux pixels qui bougent le plus
    (le ballon/le tireur dominent). La ou la diff de frames se rabattait au
    centre des que la camera bougeait, on garde le ballon dans le cadre.

    Repli sur _motion_samples si le flot optique n'est pas disponible.
    """
    try:
        import cv2
        import numpy as np
    except Exception:
        return _motion_samples(cap, times, src_w, src_h)

    scale = 320.0 / src_w
    out: list[tuple[float, float] | None] = []
    grid = None
    for t in times:
        cap.set(cv2.CAP_PROP_POS_MSEC, t * 1000.0)
        ok1, f1 = cap.read()
        ok2, f2 = cap.read()
        if not (ok1 and ok2) or f1 is None or f2 is None:
            out.append(None)
            continue
        g1 = cv2.cvtColor(cv2.resize(f1, (0, 0), fx=scale, fy=scale), cv2.COLOR_BGR2GRAY)
        g2 = cv2.cvtColor(cv2.resize(f2, (0, 0), fx=scale, fy=scale), cv2.COLOR_BGR2GRAY)
        try:
            flow = cv2.calcOpticalFlowFarneback(g1, g2, None, 0.5, 3, 15, 3, 5, 1.2, 0)
        except Exception:
            out.append(None)
            continue
        fx, fy = flow[..., 0], flow[..., 1]
        # Mouvement global de la camera = mediane (panoramique/translation).
        cam_x, cam_y = float(np.median(fx)), float(np.median(fy))
        rx, ry = fx - cam_x, fy - cam_y
        mag = np.sqrt(rx * rx + ry * ry)
        # Ne garder que le mouvement local franc (joueurs/ballon), pas le bruit
        # ni le residu diffus du public. Seuil = haut percentile, avec plancher.
        thr = max(float(np.percentile(mag, 92)), 0.6)
        weight = np.where(mag >= thr, mag, 0.0)
        total = float(weight.sum())
        if total < 1e-3:
            out.append(None)  # rien de franc -> rappel au centre en aval
            continue
        if grid is None or grid[0].shape != mag.shape:
            h, w = mag.shape
            grid = np.mgrid[0:h, 0:w]
        ys, xs = grid
        cx = float((weight * xs).sum() / total) / scale
        cy = float((weight * ys).sum() / total) / scale
        out.append((cx, cy))
    return out


# --------------------------------------------------------------------------- #
# Decision de strategie par scene + construction des cles
# --------------------------------------------------------------------------- #

def _fill(values: list[tuple[float, float] | None], default: float, axis: str) -> list[float]:
    """Remplit les trous (None) par report de la derniere valeur connue, sinon defaut."""
    out: list[float] = []
    last = default
    for v in values:
        if v is not None:
            last = v[0] if axis == "x" else v[1]
        out.append(last)
    # report arriere pour les None initiaux
    nxt = default
    for i in range(len(out) - 1, -1, -1):
        if values[i] is not None:
            nxt = out[i]
        elif out[i] == default:
            out[i] = nxt
    return out


def _decide_strategy(
    face_ratio: float,
    face_size: float,
    avg_count: float = 1.0,
    face_y: float = 0.45,
    mode: str = "auto",
) -> str:
    if mode in ("face", "motion", "center"):
        return mode
    # Foule (public, tribunes) : beaucoup de visages -> pas un plan mono-orateur.
    if avg_count > 2.5:
        return "motion"
    # Visage dominant tres bas dans le cadre -> spectateur du premier rang (proche
    # camera) plutot que l'orateur sur scene -> on suit l'action.
    if face_y > 0.62:
        return "motion"
    # Un visage present et assez grand sur la majorite de la scene -> face.
    if face_ratio >= 0.5 and face_size >= 0.06:
        return "face"
    return "motion"


def compute_reframe(
    video_path: Path,
    clip_start: float,
    clip_end: float,
    *,
    models_dir: Path,
    detector: FaceDetector | None = None,
    scene_threshold: float = 27.0,
    samples_per_scene: int = 5,  # conserve pour compat ; le pas est dynamique
    per_scene: bool = True,
    mode: str = "auto",
    dt: float = 0.4,
    max_keys: int = 48,
) -> ReframePlan:
    import cv2

    src_w, src_h = _video_dimensions(video_path)

    # Mode "largeur complete" : pas de crop ni d'analyse. On garde toute la
    # largeur de la source dans une bande centrale (bandes floues au rendu).
    # Rien ne sort du cadre horizontalement : ideal pour le sport en plan large.
    if mode == "fullwidth":
        logger.info("Reframe %.1f-%.1fs : largeur complete (bandes floues).", clip_start, clip_end)
        return ReframePlan(
            src_w=src_w, src_h=src_h, crop_w=src_w, crop_h=src_h, axis="x",
            keys=[CropKey(t=0.0, x=0, y=0, scene=0)],
            strategy="fullwidth", n_scenes=1, layout="fullwidth",
        )

    crop_w, crop_h, axis = compute_crop_window(src_w, src_h)
    detector = detector or FaceDetector(models_dir)
    center_default = (src_w / 2.0) if axis == "x" else (src_h / 2.0)
    crop_size = crop_w if axis == "x" else crop_h
    src_size = src_w if axis == "x" else src_h
    const_other = 0  # l'autre axe (y si axis x) reste a 0 (pleine dimension)

    scenes = detect_scenes(video_path, clip_start, clip_end, scene_threshold) if per_scene else [(clip_start, clip_end)]

    cap = cv2.VideoCapture(str(video_path))
    keys: list[CropKey] = []
    strategies: list[str] = []

    for si, (s, e) in enumerate(scenes):
        times = _sample_times(s, e, dt)
        faces, sizes, avg_count = _face_samples(cap, detector, times)
        face_ratio = sum(1 for f in faces if f is not None) / max(1, len(faces))
        face_size = sorted(sizes)[len(sizes) // 2] if sizes else 0.0
        fys = sorted(f[1] / src_h for f in faces if f is not None)
        face_y = fys[len(fys) // 2] if fys else 0.45
        strat = _decide_strategy(face_ratio, face_size, avg_count, face_y, mode)

        if strat == "face":
            centers = faces
        elif strat == "motion":
            centers = _action_samples(cap, times, src_w, src_h)
        else:
            centers = [None] * len(times)
        strategies.append(strat)

        coords = _fill(centers, center_default, axis)
        if strat == "face":
            # Rappel vers le centre quand le visage est petit (plan large avec
            # public) : on evite de courir vers un visage de spectateur. Gros
            # plan (visage large) -> suivi precis ; petit visage -> proche centre.
            pull = max(0.0, min(1.0, (face_size - 0.05) / 0.10))
            coords = [pull * c + (1.0 - pull) * center_default for c in coords]
        # Sport (motion) : l'action traverse vite -> pan plus rapide et moins
        # lisse pour rester sur le ballon. Talking-head : pan lent et tres doux.
        if strat == "motion":
            sm_win, step_frac = 3, 0.22
        else:
            sm_win, step_frac = 5, 0.09
        max_step = step_frac * src_size * dt
        coords = smooth_series(coords, win=sm_win, max_step=max_step)
        origins = [clamp_origin(c, crop_size, src_size) for c in coords]

        # Reduction en cles (sous-echantillonnage borne, division plafond).
        budget = max(2, max_keys // max(1, len(scenes)))
        step = max(1, (len(origins) + budget - 1) // budget)
        idxs = list(range(0, len(origins), step))
        if idxs[-1] != len(origins) - 1:
            idxs.append(len(origins) - 1)
        for i in idxs:
            t_local = round(times[i] - clip_start, 3)
            val = origins[i]
            x = val if axis == "x" else const_other
            y = const_other if axis == "x" else val
            keys.append(CropKey(t=t_local, x=x, y=y, scene=si))

    cap.release()

    # Au moins une cle.
    if not keys:
        keys = [CropKey(t=0.0, x=clamp_origin(center_default, crop_size, src_size) if axis == "x" else const_other,
                        y=const_other if axis == "x" else clamp_origin(center_default, crop_size, src_size),
                        scene=0)]
    keys.sort(key=lambda k: k.t)
    dominant = max(set(strategies), key=strategies.count) if strategies else "center"
    logger.info(
        "Reframe %.1f-%.1fs : %d scene(s), strategie %s, %d cles, crop %dx%d (axe %s).",
        clip_start, clip_end, len(scenes), dominant, len(keys), crop_w, crop_h, axis,
    )
    return ReframePlan(
        src_w=src_w, src_h=src_h, crop_w=crop_w, crop_h=crop_h, axis=axis,
        keys=keys, strategy=dominant, n_scenes=len(scenes),
    )
