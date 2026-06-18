"""Tests de la geometrie de recadrage (sans dependance video)."""

from __future__ import annotations

from clipper.reframe import _decide_strategy, clamp_origin, compute_crop_window, smooth_series


def test_crop_window_landscape_16_9():
    w, h, axis = compute_crop_window(1920, 1080)
    assert axis == "x"
    assert h == 1080
    assert w % 2 == 0
    # ratio proche de 9/16
    assert abs((w / h) - (9 / 16)) < 0.01
    assert w < 1920  # on a bien retreci horizontalement


def test_crop_window_720p():
    w, h, axis = compute_crop_window(1280, 720)
    assert axis == "x"
    assert h == 720
    assert abs((w / h) - (9 / 16)) < 0.01


def test_crop_window_tall_source():
    # Source plus etroite que 9:16 -> on glisse verticalement.
    w, h, axis = compute_crop_window(1080, 2400)
    assert axis == "y"
    assert w == 1080
    assert abs((w / h) - (9 / 16)) < 0.01


def test_clamp_origin_centers():
    # centre 1000, fenetre 608 sur 1920 -> 696, dans les bornes
    assert clamp_origin(1000, 608, 1920) == 696


def test_clamp_origin_left_edge():
    assert clamp_origin(50, 608, 1920) == 0


def test_clamp_origin_right_edge():
    assert clamp_origin(1900, 608, 1920) == 1920 - 608


def test_smooth_clamps_velocity():
    # Saut brutal 0 -> 1000 borne a 100/echantillon (pan fluide, pas de whip).
    out = smooth_series([0, 0, 1000, 1000, 1000], win=1, max_step=100)
    for a, b in zip(out, out[1:]):
        assert abs(b - a) <= 100 + 1e-6


def test_smooth_averages():
    out = smooth_series([0, 100, 0, 100, 0], win=5, max_step=None)
    # la moyenne glissante reduit l'amplitude
    assert max(out) < 100


def test_decide_strategy_face_when_present_and_large():
    assert _decide_strategy(face_ratio=0.8, face_size=0.15, mode="auto") == "face"


def test_decide_strategy_motion_when_faces_sparse():
    # Peu de visages (cas foot / action) -> mouvement.
    assert _decide_strategy(face_ratio=0.2, face_size=0.30, mode="auto") == "motion"


def test_decide_strategy_respects_forced_mode():
    assert _decide_strategy(face_ratio=0.9, face_size=0.5, mode="motion") == "motion"
    assert _decide_strategy(face_ratio=0.0, face_size=0.0, mode="face") == "face"
