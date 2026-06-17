"""Tests du parsing LLM et de la validation/alignement des segments."""

from __future__ import annotations

import pytest

from clipper.segment import (
    dedup_and_rank,
    parse_llm_segments,
    SelectedSegment,
    snap_to_boundaries,
    validate_segments,
)
from clipper.transcribe import TSegment, Transcript, Word


def _transcript() -> Transcript:
    segs = []
    t = 0.0
    for i in range(20):
        start, end = t, t + 3.0
        words = [Word(start=start + k * 0.5, end=start + (k + 1) * 0.5, text=f"m{k}") for k in range(6)]
        segs.append(TSegment(start=start, end=end, text=f"phrase {i}", words=words))
        t = end
    return Transcript(language="fr", duration=t, segments=segs)


def test_parse_plain_array():
    txt = '[{"start": 1.0, "end": 2.0, "title": "a", "hook_score": 80, "reason": "x"}]'
    out = parse_llm_segments(txt)
    assert len(out) == 1 and out[0]["start"] == 1.0


def test_parse_markdown_fence():
    txt = "Voici les clips :\n```json\n[{\"start\":1,\"end\":2,\"title\":\"a\",\"hook_score\":5,\"reason\":\"r\"}]\n```\nVoila."
    out = parse_llm_segments(txt)
    assert out[0]["title"] == "a"


def test_parse_with_think_block_and_noise():
    txt = '<think>je reflechis [ignore]</think> blabla [{"start":3,"end":9,"title":"t","hook_score":70,"reason":"r"}] fin'
    out = parse_llm_segments(txt)
    assert len(out) == 1 and out[0]["end"] == 9


def test_parse_single_object_becomes_list():
    txt = '{"start":1,"end":2,"title":"a","hook_score":50,"reason":"r"}'
    out = parse_llm_segments(txt)
    assert isinstance(out, list) and len(out) == 1


def test_parse_invalid_raises():
    with pytest.raises(ValueError):
        parse_llm_segments("desole, je ne peux pas")


def test_snap_to_boundaries():
    tr = _transcript()
    # 4.2 -> debut du segment a 3.0 ; 13.7 -> fin du segment a 15.0
    start, end = snap_to_boundaries(4.2, 13.7, tr.segments)
    assert start == 3.0
    assert end == 15.0


def test_validate_enforces_duration_bounds():
    tr = _transcript()
    raw = [{"start": 2.0, "end": 5.0, "title": "court", "hook_score": 90, "reason": "r"}]
    out = validate_segments(raw, tr, min_dur=20, max_dur=60)
    assert len(out) == 1
    assert out[0].duration() >= 20  # etendu jusqu'a >= min_duration


def test_validate_clamps_overlong():
    tr = _transcript()
    raw = [{"start": 0.0, "end": 59.0, "title": "long", "hook_score": 90, "reason": "r"}]
    out = validate_segments(raw, tr, min_dur=20, max_dur=40)
    assert out[0].duration() <= 40


def test_dedup_removes_overlaps():
    segs = [
        SelectedSegment(0, 30, "a", 90, "r"),
        SelectedSegment(5, 32, "b", 80, "r"),   # chevauche a -> ecarte
        SelectedSegment(40, 70, "c", 70, "r"),
    ]
    kept = dedup_and_rank(segs, n=8)
    titles = {s.title for s in kept}
    assert titles == {"a", "c"}
