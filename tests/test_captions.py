"""Tests de generation des sous-titres ASS karaoke."""

from __future__ import annotations

from clipper.captions import format_ass_time, generate_ass_for_clip, group_into_lines, WordTiming
from clipper.transcribe import Word


def test_format_ass_time():
    assert format_ass_time(0) == "0:00:00.00"
    assert format_ass_time(65.42) == "0:01:05.42"
    assert format_ass_time(3661.5) == "1:01:01.50"


def test_group_into_lines_respects_max_words():
    words = [WordTiming(i * 0.3, i * 0.3 + 0.25, f"w{i}") for i in range(10)]
    lines = group_into_lines(words, max_words=4, max_gap=5.0)
    assert all(len(line) <= 4 for line in lines)
    assert sum(len(line) for line in lines) == 10


def test_group_splits_on_pause():
    words = [
        WordTiming(0.0, 0.4, "a"),
        WordTiming(0.5, 0.9, "b"),
        WordTiming(3.0, 3.4, "c"),  # grande pause -> nouvelle ligne
    ]
    lines = group_into_lines(words, max_words=10, max_gap=0.6)
    assert len(lines) == 2


def test_generate_ass_rebases_and_highlights():
    words = [
        Word(start=100.0, end=100.4, text="Bonjour"),
        Word(start=100.4, end=100.9, text="tout"),
        Word(start=100.9, end=101.3, text="le"),
        Word(start=101.3, end=101.8, text="monde"),
    ]
    ass = generate_ass_for_clip(words, clip_start=100.0, clip_end=130.0)
    assert "[Script Info]" in ass
    assert "PlayResX: 1080" in ass
    assert "Dialogue:" in ass
    # rebase : le premier evenement commence pres de 0, pas de 100s
    assert "0:00:00.0" in ass
    assert "1:40:00" not in ass
    # surlignage du mot actif present
    assert "\\fscx112" in ass


def test_generate_ass_filters_out_of_range_words():
    words = [
        Word(start=10.0, end=10.4, text="avant"),
        Word(start=105.0, end=105.4, text="dedans"),
        Word(start=200.0, end=200.4, text="apres"),
    ]
    ass = generate_ass_for_clip(words, clip_start=100.0, clip_end=130.0)
    assert "dedans" in ass
    assert "avant" not in ass
    assert "apres" not in ass
