"""Etape 5 : recadrage 16:9 -> 9:16 centre sur le visage dominant.

Par clip : decoupe en scenes (PySceneDetect), echantillonne quelques frames par
scene, detecte le visage dominant (MediaPipe Tasks FaceDetector, fallback OpenCV
Haar), calcule une fenetre de crop 9:16 centree sur ce visage et clampee aux
bords. Au MVP un crop statique par scene suffit.

Fallbacks : pas de visage exploitable -> crop centre. Detection indisponible ->
crop centre. Modele MediaPipe non telechargeable (hors-ligne) -> Haar OpenCV.

TODO phase 2 : active speaker tracking (croiser activite audio + position du
visage) et pan panoramique fluide entre frames au lieu d'un crop fixe par scene.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger("clipper.reframe")

FACE_MODEL_URL = (
    "https://storage.googleapis.com/mediapipe-models/face_detector/"
    "blaze_face_short_range/float16/1/blaze_face_short_range.tflite"
)
FACE_MODEL_NAME = "blaze_face_short_range.tflite"


@dataclass
class SceneCrop:
    """Fenetre de crop pour une scene. Temps en secondes RELATIFS au clip."""

    t0: float
    t1: float
    x: int
    y: int
    w: int
    h: int


@dataclass
class ReframePlan:
    src_w: int
    src_h: int
    crop_w: int
    crop_h: int
    axis: str  # "x" (panoramique horizontal) ou "y" (vertical)
    scenes: list[SceneCrop]


# --------------------------------------------------------------------------- #
# Geometrie du crop (testable sans dependances lourdes)
# --------------------------------------------------------------------------- #

def compute_crop_window(src_w: int, src_h: int, ratio_w: int = 9, ratio_h: int = 16) -> tuple[int, int, str]:
    """Calcule la taille de la fenetre 9:16 a extraire et l'axe de deplacement.

    Renvoie (crop_w, crop_h, axis). axis='x' si on glisse horizontalement
    (source plus large que 9:16, cas classique 16:9), sinon 'y'.
    """
    target = ratio_w / ratio_h
    source = src_w / src_h
    if source >= target:
        # Source plus large : pleine hauteur, largeur reduite, on glisse en x.
        crop_h = src_h
        crop_w = int(round(src_h * target))
        axis = "x"
    else:
        # Source plus etroite : pleine largeur, hauteur reduite, on glisse en y.
        crop_w = src_w
        crop_h = int(round(src_w / target))
        axis = "y"
    crop_w = min(src_w, crop_w - (crop_w % 2))
    crop_h = min(src_h, crop_h - (crop_h % 2))
    return crop_w, crop_h, axis


def clamp_origin(center: float, crop_size: int, src_size: int) -> int:
    """Coin haut-gauche du crop, centre sur `center`, clampe dans [0, src-crop]."""
    origin = int(round(center - crop_size / 2))
    origin = max(0, min(origin, src_size - crop_size))
    return origin


# --------------------------------------------------------------------------- #
# Detection de visage (MediaPipe Tasks, fallback Haar OpenCV)
# --------------------------------------------------------------------------- #

def ensure_face_model(models_dir: Path) -> Path | None:
    """Garantit la presence du modele MediaPipe ; le telecharge une fois si besoin."""
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
    except Exception as exc:  # offline, blocage reseau, etc.
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
        self.backend = "mediapipe" if self._mp is not None else (
            "haar" if self._haar is not None else "none"
        )
        logger.info("Detecteur de visage : %s", self.backend)

    @staticmethod
    def _try_load_mediapipe(model_path: Path, min_conf: float):
        try:
            from mediapipe.tasks import python as mpp
            from mediapipe.tasks.python import vision

            base = mpp.BaseOptions(model_asset_path=str(model_path))
            opts = vision.FaceDetectorOptions(
                base_options=base, min_detection_confidence=min_conf
            )
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

    def center(self, frame_bgr) -> tuple[float, float, float] | None:
        """Renvoie (cx, cy, aire) du visage dominant en pixels, ou None."""
        if self._mp is not None:
            return self._center_mediapipe(frame_bgr)
        if self._haar is not None:
            return self._center_haar(frame_bgr)
        return None

    def _center_mediapipe(self, frame_bgr):
        import cv2
        import mediapipe as mp

        rgb = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB)
        mp_img = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb)
        res = self._mp.detect(mp_img)
        if not res.detections:
            return None
        best = None
        for det in res.detections:
            b = det.bounding_box
            area = float(b.width * b.height)
            if best is None or area > best[2]:
                best = (b.origin_x + b.width / 2.0, b.origin_y + b.height / 2.0, area)
        return best

    def _center_haar(self, frame_bgr):
        import cv2

        gray = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2GRAY)
        faces = self._haar.detectMultiScale(gray, scaleFactor=1.1, minNeighbors=5, minSize=(60, 60))
        if len(faces) == 0:
            return None
        x, y, w, h = max(faces, key=lambda f: f[2] * f[3])
        return (x + w / 2.0, y + h / 2.0, float(w * h))


# --------------------------------------------------------------------------- #
# Detection de scenes
# --------------------------------------------------------------------------- #

def detect_scenes(video_path: Path, start: float, end: float, threshold: float) -> list[tuple[float, float]]:
    """Scenes (en secondes absolues) dans [start, end]. Replis : une scene unique."""
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
# Calcul du plan de recadrage
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


def _dominant_center(
    video_path: Path, detector: FaceDetector, t_start: float, t_end: float, samples: int
) -> tuple[float, float] | None:
    """Centre median des visages sur quelques frames echantillonnees dans la scene."""
    import cv2

    cap = cv2.VideoCapture(str(video_path))
    times = [t_start + (t_end - t_start) * (i + 0.5) / samples for i in range(max(1, samples))]
    centers_x: list[float] = []
    centers_y: list[float] = []
    for t in times:
        cap.set(cv2.CAP_PROP_POS_MSEC, t * 1000.0)
        ok, frame = cap.read()
        if not ok or frame is None:
            continue
        found = detector.center(frame)
        if found is not None:
            centers_x.append(found[0])
            centers_y.append(found[1])
    cap.release()
    if not centers_x:
        return None
    centers_x.sort()
    centers_y.sort()
    mid = len(centers_x) // 2
    return centers_x[mid], centers_y[mid]


def compute_reframe(
    video_path: Path,
    clip_start: float,
    clip_end: float,
    *,
    models_dir: Path,
    detector: FaceDetector | None = None,
    scene_threshold: float = 27.0,
    samples_per_scene: int = 5,
    per_scene: bool = True,
) -> ReframePlan:
    src_w, src_h = _video_dimensions(video_path)
    crop_w, crop_h, axis = compute_crop_window(src_w, src_h)
    detector = detector or FaceDetector(models_dir)

    if per_scene:
        scenes = detect_scenes(video_path, clip_start, clip_end, scene_threshold)
    else:
        scenes = [(clip_start, clip_end)]

    scene_crops: list[SceneCrop] = []
    for s, e in scenes:
        center = _dominant_center(video_path, detector, s, e, samples_per_scene)
        if center is None:
            # Fallback crop centre.
            cx, cy = src_w / 2.0, src_h / 2.0
        else:
            cx, cy = center
        if axis == "x":
            x = clamp_origin(cx, crop_w, src_w)
            y = 0
        else:
            x = 0
            y = clamp_origin(cy, crop_h, src_h)
        scene_crops.append(
            SceneCrop(
                t0=round(s - clip_start, 3),
                t1=round(e - clip_start, 3),
                x=x,
                y=y,
                w=crop_w,
                h=crop_h,
            )
        )

    logger.info(
        "Reframe %.1f-%.1fs : %d scene(s), crop %dx%d (axe %s).",
        clip_start, clip_end, len(scene_crops), crop_w, crop_h, axis,
    )
    return ReframePlan(src_w=src_w, src_h=src_h, crop_w=crop_w, crop_h=crop_h, axis=axis, scenes=scene_crops)
