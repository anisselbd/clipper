"""Tests de construction du filtre crop ffmpeg (chemin keyframes)."""

from __future__ import annotations

from clipper.reframe import CropKey, ReframePlan
from clipper.render import build_crop_filter, build_filtergraph


def _plan(keys, axis="x", cw=608, ch=1080):
    return ReframePlan(src_w=1920, src_h=1080, crop_w=cw, crop_h=ch, axis=axis, keys=keys)


def test_single_key_constant_crop():
    f = build_crop_filter(_plan([CropKey(0.0, 200, 0, 0)]))
    assert f == "crop=608:1080:200:0"
    assert "," not in f  # aucun risque de mauvais parsing


def test_same_x_keys_collapse_to_constant():
    f = build_crop_filter(_plan([CropKey(0.0, 200, 0, 0), CropKey(5.0, 200, 0, 0)]))
    assert f == "crop=608:1080:200:0"


def test_same_scene_interpolates():
    f = build_crop_filter(_plan([CropKey(0.0, 100, 0, 0), CropKey(5.0, 500, 0, 0)]))
    assert "if(lt(t\\," in f
    assert "*(t-" in f  # terme d'interpolation lineaire (pan fluide)
    assert "100" in f and "500" in f


def test_cross_scene_is_a_step_not_a_pan():
    # Scenes differentes -> palier (saut), pas d'interpolation a travers la coupe.
    f = build_crop_filter(_plan([CropKey(0.0, 100, 0, 0), CropKey(5.0, 500, 0, 1)]))
    assert "if(lt(t\\," in f
    assert "*(t-" not in f  # pas d'interpolation entre deux scenes


def test_vertical_axis_varies_y():
    plan = _plan([CropKey(0.0, 0, 100, 0), CropKey(4.0, 0, 400, 0)], axis="y", cw=1080, ch=1920)
    f = build_crop_filter(plan)
    assert f.startswith("crop=1080:1920:0:")  # x constant, y interpole


def test_filtergraph_contains_scale_and_ass():
    g = build_filtergraph(_plan([CropKey(0.0, 200, 0, 0)]), "subs.ass", 1080, 1920)
    assert "scale=1080:1920" in g
    assert "ass=subs.ass" in g
