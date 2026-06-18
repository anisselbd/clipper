"""Interface StorageProvider : stockage des artefacts (clips, vignettes).

Point de bascule SaaS n.2. Le front ne manipule JAMAIS de chemin local : il lit
toujours une URL renvoyee par get_url(). En local cette URL pointe vers l'API
(localhost), en cloud vers une URL presignee R2/S3. Contrat identique.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path


class StorageProvider(ABC):
    @abstractmethod
    def save(self, local_path: Path, key: str) -> str:
        """Enregistre un fichier sous `key` et renvoie son URL publique."""

    @abstractmethod
    def get_url(self, key: str) -> str:
        """URL publique pour acceder au fichier `key`."""

    @abstractmethod
    def path_for(self, key: str) -> Path | None:
        """Chemin local du fichier si applicable (None en cloud)."""

    @abstractmethod
    def exists(self, key: str) -> bool:
        ...

    @abstractmethod
    def delete(self, key: str) -> None:
        ...
