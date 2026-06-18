"""JobStore SQLite : jobs et clips persistes localement."""

from __future__ import annotations

import json
import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path

from .base import JobStore


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class SqliteJobStore(JobStore):
    def __init__(self, db_path: Path) -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._conn = sqlite3.connect(str(self.db_path), check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL;")
        self._init_schema()

    def _init_schema(self) -> None:
        with self._lock:
            self._conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS jobs (
                    id TEXT PRIMARY KEY,
                    url TEXT NOT NULL,
                    params TEXT NOT NULL,
                    status TEXT NOT NULL,
                    step TEXT,
                    progress REAL DEFAULT 0,
                    error TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS clips (
                    id TEXT PRIMARY KEY,
                    job_id TEXT NOT NULL,
                    clip_id TEXT NOT NULL,
                    order_index INTEGER DEFAULT 0,
                    title TEXT,
                    hook_score INTEGER,
                    duration REAL,
                    width INTEGER,
                    height INTEGER,
                    start REAL,
                    "end" REAL,
                    reason TEXT,
                    selection_source TEXT,
                    file_key TEXT,
                    thumb_key TEXT,
                    social TEXT,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY (job_id) REFERENCES jobs(id)
                );
                CREATE INDEX IF NOT EXISTS idx_clips_job ON clips(job_id);
                """
            )
            # Migration douce pour les bases creees avant la colonne social.
            try:
                self._conn.execute("ALTER TABLE clips ADD COLUMN social TEXT")
            except sqlite3.OperationalError:
                pass
            self._conn.commit()

    # --- jobs ---

    def create_job(self, job_id: str, url: str, params: dict) -> dict:
        now = _now()
        with self._lock:
            self._conn.execute(
                "INSERT INTO jobs (id, url, params, status, step, progress, created_at, updated_at) "
                "VALUES (?, ?, ?, 'queued', NULL, 0, ?, ?)",
                (job_id, url, json.dumps(params), now, now),
            )
            self._conn.commit()
        return self.get_job(job_id)

    def get_job(self, job_id: str) -> dict | None:
        with self._lock:
            row = self._conn.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()
        return self._job_row(row) if row else None

    def update_job(self, job_id: str, **fields) -> dict | None:
        if not fields:
            return self.get_job(job_id)
        allowed = {"status", "step", "progress", "error"}
        sets = {k: v for k, v in fields.items() if k in allowed}
        sets["updated_at"] = _now()
        cols = ", ".join(f'"{k}" = ?' for k in sets)
        with self._lock:
            self._conn.execute(f"UPDATE jobs SET {cols} WHERE id = ?", (*sets.values(), job_id))
            self._conn.commit()
        return self.get_job(job_id)

    def list_jobs(self) -> list[dict]:
        with self._lock:
            rows = self._conn.execute("SELECT * FROM jobs ORDER BY created_at DESC").fetchall()
        return [self._job_row(r) for r in rows]

    # --- clips ---

    def add_clip(self, job_id: str, clip: dict) -> dict:
        clip_id = clip["clip_id"]
        gid = f"{job_id}_{clip_id}"
        social = clip.get("social")
        with self._lock:
            self._conn.execute(
                'INSERT OR REPLACE INTO clips (id, job_id, clip_id, order_index, title, hook_score, '
                'duration, width, height, start, "end", reason, selection_source, file_key, thumb_key, social, created_at) '
                "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (
                    gid, job_id, clip_id, clip.get("order_index", 0), clip.get("title"),
                    clip.get("hook_score"), clip.get("duration"), clip.get("width"), clip.get("height"),
                    clip.get("start"), clip.get("end"), clip.get("reason"), clip.get("selection_source"),
                    clip.get("file_key"), clip.get("thumb_key"),
                    json.dumps(social, ensure_ascii=False) if social is not None else None,
                    _now(),
                ),
            )
            self._conn.commit()
        return self.get_clip(gid)

    def get_clip(self, clip_id: str) -> dict | None:
        with self._lock:
            row = self._conn.execute("SELECT * FROM clips WHERE id = ?", (clip_id,)).fetchone()
        return self._clip_row(row) if row else None

    def list_clips(self, job_id: str) -> list[dict]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT * FROM clips WHERE job_id = ? ORDER BY order_index", (job_id,)
            ).fetchall()
        return [self._clip_row(r) for r in rows]

    @staticmethod
    def _clip_row(row: sqlite3.Row) -> dict:
        d = dict(row)
        if d.get("social"):
            try:
                d["social"] = json.loads(d["social"])
            except (json.JSONDecodeError, TypeError):
                d["social"] = None
        return d

    @staticmethod
    def _job_row(row: sqlite3.Row) -> dict:
        d = dict(row)
        try:
            d["params"] = json.loads(d.get("params") or "{}")
        except (json.JSONDecodeError, TypeError):
            d["params"] = {}
        return d
