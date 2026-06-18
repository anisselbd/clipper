"""Tests de la detection de temps forts audio (sur signaux synthetiques)."""

from __future__ import annotations

import numpy as np

from clipper.highlights import find_audio_peaks


def _times(n, hop=0.2):
    return np.arange(n) * hop


def test_detects_sustained_loud_region():
    db = np.full(200, -30.0)
    db[100:115] = -10.0  # 15 echantillons * 0.2s = 3s soutenus, +20 dB
    peaks = find_audio_peaks(_times(200), db, hop=0.2, min_prominence=6, sustain=1.6)
    assert len(peaks) == 1
    assert 19.0 < peaks[0].t < 23.0
    assert peaks[0].prominence > 15.0


def test_flat_audio_no_peaks():
    db = np.full(200, -25.0)
    assert find_audio_peaks(_times(200), db) == []


def test_short_spike_ignored():
    db = np.full(200, -30.0)
    db[100:102] = -5.0  # 0.4s seulement, sous le seuil de duree
    assert find_audio_peaks(_times(200), db, sustain=1.6) == []


def test_nearby_peaks_merge():
    db = np.full(300, -30.0)
    db[50:60] = -10.0
    db[70:80] = -8.0  # deux regions a ~4s d'ecart -> fusionnees
    peaks = find_audio_peaks(_times(300), db, min_gap=12.0)
    assert len(peaks) == 1
    assert peaks[0].prominence > 20.0  # garde la plus forte (-8 dB)
