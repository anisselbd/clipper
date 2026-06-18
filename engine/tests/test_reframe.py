"""Tests de la geometrie de recadrage (sans dependance video)."""

from __future__ import annotations

from clipper.reframe import clamp_origin, compute_crop_window


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
