"""STUB cloud (phase 2) : JobStore Supabase / Postgres."""

from __future__ import annotations

from .base import JobStore


class SupabaseJobStore(JobStore):
    name = "supabase"

    def __init__(self, url: str | None = None, key: str | None = None) -> None:
        self.url = url
        self.key = key

    # TODO (phase 2) : memes operations CRUD que SqliteJobStore mais via le
    # client Supabase (tables jobs/clips, RLS par utilisateur). Le schema est
    # identique ; seul le backend de persistance change.
    def create_job(self, job_id, url, params):  # noqa: D401
        raise NotImplementedError("SupabaseJobStore : stub phase 2.")

    def get_job(self, job_id):
        raise NotImplementedError("SupabaseJobStore : stub phase 2.")

    def update_job(self, job_id, **fields):
        raise NotImplementedError("SupabaseJobStore : stub phase 2.")

    def list_jobs(self):
        raise NotImplementedError("SupabaseJobStore : stub phase 2.")

    def add_clip(self, job_id, clip):
        raise NotImplementedError("SupabaseJobStore : stub phase 2.")

    def get_clip(self, clip_id):
        raise NotImplementedError("SupabaseJobStore : stub phase 2.")

    def list_clips(self, job_id):
        raise NotImplementedError("SupabaseJobStore : stub phase 2.")
