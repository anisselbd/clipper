"""Tests du JobStore SQLite (CRUD jobs + clips)."""

from __future__ import annotations

from clipper.providers.jobstore.sqlite import SqliteJobStore


def _store(tmp_path):
    return SqliteJobStore(tmp_path / "test.db")


def test_create_and_get_job(tmp_path):
    s = _store(tmp_path)
    s.create_job("job1", "https://x", {"num_clips": 5})
    job = s.get_job("job1")
    assert job["status"] == "queued"
    assert job["url"] == "https://x"
    assert job["params"]["num_clips"] == 5


def test_update_job_status_and_progress(tmp_path):
    s = _store(tmp_path)
    s.create_job("job1", "u", {})
    s.update_job("job1", status="running", step="transcribing", progress=0.3)
    job = s.get_job("job1")
    assert job["status"] == "running"
    assert job["step"] == "transcribing"
    assert abs(job["progress"] - 0.3) < 1e-6


def test_add_and_list_clips(tmp_path):
    s = _store(tmp_path)
    s.create_job("job1", "u", {})
    s.add_clip("job1", {"clip_id": "clip_00", "order_index": 0, "title": "A", "hook_score": 80, "file_key": "k0"})
    s.add_clip("job1", {"clip_id": "clip_01", "order_index": 1, "title": "B", "hook_score": 90, "file_key": "k1"})
    clips = s.list_clips("job1")
    assert len(clips) == 2
    assert clips[0]["clip_id"] == "clip_00"
    assert s.get_clip("job1_clip_01")["title"] == "B"


def test_unknown_job_is_none(tmp_path):
    s = _store(tmp_path)
    assert s.get_job("nope") is None
