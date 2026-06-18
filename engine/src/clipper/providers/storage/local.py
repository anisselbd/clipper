"""Stockage local : fichiers sous un data dir, servis par l'API en localhost."""

from __future__ import annotations

import shutil
from pathlib import Path

from .base import StorageProvider


class LocalStorage(StorageProvider):
    def __init__(self, root: Path, public_base_url: str) -> None:
        self.root = Path(root).resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        self.public_base_url = public_base_url.rstrip("/")

    def _full(self, key: str) -> Path:
        return self.root / key.lstrip("/")

    def save(self, local_path: Path, key: str) -> str:
        local_path = Path(local_path).resolve()
        dest = self._full(key)
        # Si le fichier est deja sous le data dir (cas du pipeline), pas de copie.
        if local_path != dest.resolve():
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(local_path, dest)
        return self.get_url(key)

    def get_url(self, key: str) -> str:
        return f"{self.public_base_url}/files/{key.lstrip('/')}"

    def path_for(self, key: str) -> Path | None:
        return self._full(key)

    def exists(self, key: str) -> bool:
        return self._full(key).exists()

    def delete(self, key: str) -> None:
        p = self._full(key)
        if p.exists():
            p.unlink()

    def key_for_path(self, path: Path) -> str:
        """Cle relative au data dir pour un fichier deja ecrit dessous."""
        return str(Path(path).resolve().relative_to(self.root)).replace("\\", "/")
