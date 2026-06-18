"""Provider de stockage (local par defaut, stub cloud R2/S3)."""

from __future__ import annotations

from ...config import Config
from .base import StorageProvider
from .local import LocalStorage

__all__ = ["StorageProvider", "LocalStorage", "get_storage_provider"]


def get_storage_provider(config: Config) -> StorageProvider:
    return LocalStorage(root=config.data_dir, public_base_url=config.public_base_url)
