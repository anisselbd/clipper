"""Provider de persistance (SQLite par defaut, stub cloud Supabase)."""

from __future__ import annotations

from ...config import Config
from .base import JobStore
from .sqlite import SqliteJobStore

__all__ = ["JobStore", "SqliteJobStore", "get_job_store"]


def get_job_store(config: Config) -> JobStore:
    return SqliteJobStore(config.db_path)
