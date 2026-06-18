"""Interface JobStore : persistance des jobs et des clips.

Point de bascule SaaS n.4. En local : SQLite. En cloud : Supabase/Postgres.
Les enregistrements ne stockent que des CLES de stockage (file_key/thumb_key),
jamais d'URL absolue : l'URL est calculee par le StorageProvider a la lecture.
"""

from __future__ import annotations

from abc import ABC, abstractmethod


class JobStore(ABC):
    @abstractmethod
    def create_job(self, job_id: str, url: str, params: dict) -> dict: ...

    @abstractmethod
    def get_job(self, job_id: str) -> dict | None: ...

    @abstractmethod
    def update_job(self, job_id: str, **fields) -> dict | None: ...

    @abstractmethod
    def list_jobs(self) -> list[dict]: ...

    @abstractmethod
    def add_clip(self, job_id: str, clip: dict) -> dict: ...

    @abstractmethod
    def get_clip(self, clip_id: str) -> dict | None: ...

    @abstractmethod
    def list_clips(self, job_id: str) -> list[dict]: ...
