"""Tests de construction du filtre crop ffmpeg."""

from __future__ import annotations

from clipper.reframe import ReframePlan, SceneCrop
from clipper.render import build_crop_filter, build_filtergraph


def _plan(scenes, axis="x", cw=608, ch=1080):
    return ReframePlan(src_w=1920, src_h=1080, crop_w=cw, crop_h=ch, axis=axis, scenes=scenes)


def test_single_scene_constant_crop():
    plan = _plan([SceneCrop(0, 30, 200, 0, 608, 1080)])
    f = build_crop_filter(plan)
    assert f == "crop=608:1080:200:0"
    assert "," not in f  # aucun risque de mauvais parsing


def test_same_x_scenes_collapse_to_constant():
    plan = _plan([SceneCrop(0, 10, 200, 0, 608, 1080), SceneCrop(10, 20, 200, 0, 608, 1080)])
    assert build_crop_filter(plan) == "crop=608:1080:200:0"


def test_multi_scene_uses_escaped_expression():
    plan = _plan([SceneCrop(0, 10, 100, 0, 608, 1080), SceneCrop(10, 20, 500, 0, 608, 1080)])
    f = build_crop_filter(plan)
    assert "if(between(t\\," in f
    assert "100" in f and "500" in f


def test_filtergraph_contains_scale_and_ass():
    plan = _plan([SceneCrop(0, 30, 200, 0, 608, 1080)])
    g = build_filtergraph(plan, "subs.ass", 1080, 1920)
    assert "scale=1080:1920" in g
    assert "ass=subs.ass" in g
