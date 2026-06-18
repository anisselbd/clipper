"""Tests du kit social (hashtags, plateformes, fallback heuristique)."""

from __future__ import annotations

from clipper.social import SocialKit, _heuristic_kit, _normalize_hashtags


def test_normalize_hashtags_adds_prefix_and_dedups():
    out = _normalize_hashtags(["football", "#Goal", "goal", "  ", "#football"])
    assert out[0] == "#football"
    assert "#Goal" in out
    # dedup insensible a la casse
    assert sum(1 for t in out if t.lower() == "#football") == 1
    assert sum(1 for t in out if t.lower() == "#goal") == 1


def test_normalize_caps_at_8():
    out = _normalize_hashtags([f"#tag{i}" for i in range(20)])
    assert len(out) == 8


def test_heuristic_kit_sport():
    k = _heuristic_kit({"clip_id": "clip_00", "title": "But de Messi", "text": "goal goal football"})
    assert k.source == "heuristic"
    assert any("football" in t.lower() for t in k.hashtags)
    assert k.clip_id == "clip_00"


def test_for_platform_tiktok_adds_fyp():
    k = SocialKit(clip_id="c", caption="Hello", youtube_title="Hi", hashtags=["#a"])
    tiktok = k.for_platform("tiktok")["caption"]
    assert "#fyp" in tiktok
    assert "#a" in tiktok


def test_for_platform_shorts_has_title_and_description():
    k = SocialKit(clip_id="c", caption="Hello", youtube_title="Mon titre", hashtags=["#a"])
    sh = k.for_platform("shorts")
    assert sh["title"] == "Mon titre"
    assert "#shorts" in sh["description"]


def test_to_post_text_contains_all_platforms():
    k = SocialKit(clip_id="c", caption="Hello", youtube_title="T", hashtags=["#a"])
    txt = k.to_post_text()
    assert "TikTok" in txt and "Reels" in txt and "YouTube Shorts" in txt
