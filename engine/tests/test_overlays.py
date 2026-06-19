"""Tests des fonctions pures de detection/masquage de logo (sans video)."""

from clipper.overlays import _merge_overlapping, build_delogo_chain


def test_build_delogo_chain_empty():
    assert build_delogo_chain([]) == ""


def test_build_delogo_chain_one():
    assert build_delogo_chain([(10, 20, 30, 40)]) == "delogo=x=10:y=20:w=30:h=40"


def test_build_delogo_chain_multiple():
    chain = build_delogo_chain([(1, 2, 3, 4), (5, 6, 7, 8)])
    assert chain == "delogo=x=1:y=2:w=3:h=4,delogo=x=5:y=6:w=7:h=8"


def test_merge_overlapping_disjoint():
    boxes = [(0, 0, 10, 10), (100, 100, 10, 10)]
    assert len(_merge_overlapping(boxes)) == 2


def test_merge_overlapping_joins():
    # Deux rectangles qui se recouvrent -> un seul englobant.
    merged = _merge_overlapping([(0, 0, 20, 20), (10, 10, 20, 20)])
    assert merged == [(0, 0, 30, 30)]
