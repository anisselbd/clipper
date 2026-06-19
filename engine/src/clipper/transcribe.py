"""Etape 2 : transcription mot a mot via faster-whisper.

Brique non negociable du pipeline : produit des timestamps au mot, sur
lesquels reposent la selection (frontieres de phrase) et les sous-titres
karaoke. L'audio est d'abord extrait en wav 16 kHz mono via ffmpeg pour une
decodification robuste, puis transcrit.
"""

from __future__ import annotations

import logging
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

logger = logging.getLogger("clipper.transcribe")


@dataclass
class Word:
    start: float
    end: float
    text: str


@dataclass
class TSegment:
    """Segment de phrase Whisper (frontiere naturelle pour la decoupe)."""

    start: float
    end: float
    text: str
    words: list[Word] = field(default_factory=list)


@dataclass
class Transcript:
    language: str
    duration: float
    segments: list[TSegment]

    def all_words(self) -> list[Word]:
        out: list[Word] = []
        for seg in self.segments:
            out.extend(seg.words)
        return out

    def words_between(self, start: float, end: float) -> list[Word]:
        """Mots dont le centre tombe dans [start, end] (pour les sous-titres)."""
        out: list[Word] = []
        for w in self.all_words():
            mid = (w.start + w.end) / 2.0
            if start <= mid <= end:
                out.append(w)
        return out

    def as_dict(self) -> dict:
        return {
            "language": self.language,
            "duration": self.duration,
            "segments": [
                {
                    "start": s.start,
                    "end": s.end,
                    "text": s.text,
                    "words": [{"start": w.start, "end": w.end, "text": w.text} for w in s.words],
                }
                for s in self.segments
            ],
        }


def extract_audio(video_path: Path, out_wav: Path) -> Path:
    """Extrait un wav 16 kHz mono PCM (format attendu par Whisper)."""
    out_wav.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        "ffmpeg", "-y", "-i", str(video_path),
        "-vn", "-ac", "1", "-ar", "16000",
        "-c:a", "pcm_s16le", str(out_wav),
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        raise RuntimeError(f"Extraction audio ffmpeg echouee:\n{proc.stderr[-2000:]}")
    return out_wav


def transcribe(
    video_path: Path,
    *,
    model_size: str = "small",
    language: str = "fr",
    device: str = "cpu",
    compute_type: str = "int8",
    cache_dir: Path | None = None,
    on_progress=None,
) -> Transcript:
    # Import tardif : faster-whisper (et av) sont lourds a charger.
    import time

    from faster_whisper import WhisperModel

    cache_dir = cache_dir or video_path.parent
    wav = extract_audio(video_path, cache_dir / f"{video_path.stem}.16k.wav")

    logger.info("Chargement du modele Whisper '%s' (%s/%s)", model_size, device, compute_type)
    model = WhisperModel(model_size, device=device, compute_type=compute_type)

    logger.info("Transcription mot a mot en cours...")
    segments_iter, info = model.transcribe(
        str(wav),
        language=language,
        word_timestamps=True,
        vad_filter=True,
        beam_size=5,
    )

    # Duree totale connue avant d'iterer : permet une vraie progression (le
    # generateur transcrit au fil de l'eau, on rapporte seg.end / duree).
    total_s = float(getattr(info, "duration", 0.0)) or 0.0
    last_emit = 0.0

    segments: list[TSegment] = []
    for seg in segments_iter:
        words = [
            Word(start=float(w.start), end=float(w.end), text=w.word.strip())
            for w in (seg.words or [])
            if w.start is not None and w.end is not None and w.word.strip()
        ]
        segments.append(
            TSegment(start=float(seg.start), end=float(seg.end), text=seg.text.strip(), words=words)
        )
        if on_progress is not None and total_s > 0:
            now = time.monotonic()
            if now - last_emit > 0.4:  # throttle
                last_emit = now
                done_s = min(total_s, float(seg.end))
                on_progress(done_s / total_s, {
                    "kind": "transcribe", "done_s": done_s, "total_s": total_s,
                })

    duration = float(getattr(info, "duration", 0.0)) or (segments[-1].end if segments else 0.0)
    logger.info(
        "Transcription terminee : %d segments, %d mots, langue=%s",
        len(segments),
        sum(len(s.words) for s in segments),
        info.language,
    )
    return Transcript(language=info.language, duration=duration, segments=segments)
