"""Detection de temps forts par energie audio (sport, action, reactions).

Pour le sport, les moments forts (but, grosse occasion, celebration) se reperent
a l'explosion sonore : le commentateur qui hurle et la clameur du stade. On
calcule une enveloppe d'energie depuis le wav 16 kHz deja extrait pour la
transcription, et on repere les pics prominents et soutenus.

C'est complementaire de la selection texte : sur un talking-head, l'audio est
plat (pas de pics), donc la selection texte reprend la main.
"""

from __future__ import annotations

import logging
import wave
from dataclasses import dataclass
from pathlib import Path

import numpy as np

logger = logging.getLogger("clipper.highlights")


@dataclass
class AudioPeak:
    t: float           # instant du maximum (s)
    start: float       # debut de la region forte (s)
    end: float         # fin de la region forte (s)
    prominence: float  # dB au-dessus de la baseline (au maximum)


def read_wav_mono(path: Path) -> tuple[np.ndarray, int]:
    with wave.open(str(path), "rb") as w:
        sr = w.getframerate()
        ch = w.getnchannels()
        raw = w.readframes(w.getnframes())
    data = np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0
    if ch > 1:
        data = data.reshape(-1, ch).mean(axis=1)
    return data, sr


def energy_envelope(path: Path, win: float = 0.4, hop: float = 0.2) -> tuple[np.ndarray, np.ndarray]:
    """Enveloppe d'energie en dB : (instants, niveaux)."""
    data, sr = read_wav_mono(path)
    win_n = max(1, int(win * sr))
    hop_n = max(1, int(hop * sr))
    if len(data) < win_n:
        return np.array([0.0]), np.array([-90.0])
    times: list[float] = []
    db: list[float] = []
    for start in range(0, len(data) - win_n, hop_n):
        seg = data[start : start + win_n]
        rms = float(np.sqrt(np.mean(seg * seg))) + 1e-9
        db.append(20.0 * np.log10(rms))
        times.append((start + win_n / 2) / sr)
    return np.asarray(times), np.asarray(db)


def find_audio_peaks(
    times: np.ndarray,
    db: np.ndarray,
    *,
    hop: float = 0.2,
    min_prominence: float = 6.0,
    sustain: float = 1.6,
    min_gap: float = 12.0,
) -> list[AudioPeak]:
    """Regions soutenues nettement au-dessus du niveau de fond.

    min_prominence : dB au-dessus de la baseline pour compter comme temps fort.
    sustain        : duree minimale au-dessus du seuil (s) (celebration soutenue).
    min_gap        : fusionne les pics plus proches que ca (garde le plus fort).
    """
    if len(db) < 3:
        return []
    baseline = float(np.median(db))
    mad = float(np.median(np.abs(db - baseline))) + 1e-6
    threshold = baseline + max(min_prominence, 3.0 * mad)

    above = db > threshold
    peaks: list[AudioPeak] = []
    i, n = 0, len(db)
    while i < n:
        if not above[i]:
            i += 1
            continue
        j = i
        while j < n and above[j]:
            j += 1
        if (j - i) * hop >= sustain:
            region = db[i:j]
            k = i + int(np.argmax(region))
            peaks.append(
                AudioPeak(
                    t=float(times[k]),
                    start=float(times[i]),
                    end=float(times[min(j, n - 1)]),
                    prominence=float(db[k] - baseline),
                )
            )
        i = j

    # Fusionne les pics rapproches (un meme but = une seule region).
    peaks.sort(key=lambda p: p.t)
    merged: list[AudioPeak] = []
    for p in peaks:
        if merged and p.t - merged[-1].t < min_gap:
            if p.prominence > merged[-1].prominence:
                merged[-1] = p
        else:
            merged.append(p)
    merged.sort(key=lambda p: p.prominence, reverse=True)
    return merged


def detect_highlights(wav_path: Path, **kwargs) -> list[AudioPeak]:
    times, db = energy_envelope(wav_path)
    peaks = find_audio_peaks(times, db, **kwargs)
    logger.info("Temps forts audio : %d pic(s) detecte(s).", len(peaks))
    return peaks
