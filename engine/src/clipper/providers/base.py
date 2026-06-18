"""Interface commune des fournisseurs LLM.

Le LLM sert UNIQUEMENT a selectionner des segments existants (renvoie des
timestamps). Il n'invente jamais de contenu. L'interface est volontairement
minimale : un seul appel de completion texte, le reste de la logique
(construction du prompt, fenetrage, parsing) vit dans segment.py.
"""

from __future__ import annotations

from abc import ABC, abstractmethod


class ProviderUnavailable(RuntimeError):
    """Le fournisseur LLM est injoignable (reseau, serveur arrete, timeout).

    segment.py intercepte cette exception pour basculer sur le fallback
    heuristique, ce qui garantit un pipeline fonctionnel hors-ligne.
    """


class LLMProvider(ABC):
    """Contrat minimal d'un fournisseur de completion compatible OpenAI."""

    name: str = "base"

    @abstractmethod
    def complete(
        self,
        system: str,
        user: str,
        *,
        temperature: float = 0.2,
        max_tokens: int = 2048,
    ) -> str:
        """Renvoie le contenu texte de la reponse du modele.

        Doit lever ProviderUnavailable si le service est injoignable.
        """
        raise NotImplementedError
