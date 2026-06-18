"""STUB cloud (phase 2) : stockage objet R2 / S3 avec URL presignee."""

from __future__ import annotations

from pathlib import Path

from .base import StorageProvider


class CloudStorage(StorageProvider):
    name = "r2"

    def __init__(self, bucket: str | None = None, endpoint: str | None = None) -> None:
        self.bucket = bucket
        self.endpoint = endpoint

    def save(self, local_path: Path, key: str) -> str:
        # TODO (phase 2) : upload via boto3/botocore vers R2/S3, puis renvoyer
        # une URL presignee (get_url). Penser au content-type video/mp4.
        raise NotImplementedError("CloudStorage : stub phase 2 (R2/S3).")

    def get_url(self, key: str) -> str:
        # TODO (phase 2) : generer une URL presignee a duree limitee.
        raise NotImplementedError("CloudStorage : stub phase 2.")

    def path_for(self, key: str) -> Path | None:
        return None  # pas de chemin local en cloud

    def exists(self, key: str) -> bool:
        raise NotImplementedError("CloudStorage : stub phase 2.")

    def delete(self, key: str) -> None:
        raise NotImplementedError("CloudStorage : stub phase 2.")
