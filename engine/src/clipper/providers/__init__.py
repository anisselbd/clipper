"""Assemblage des 4 providers (les coutures SaaS du moteur).

Le front et l'API ne connaissent que les interfaces, jamais les implementations.
L'impl par defaut est toujours locale ; les versions cloud sont des stubs.
"""

from __future__ import annotations

from dataclasses import dataclass

from ..config import Config
from ..preflight import PreflightReport, run_preflight
from .encoder import EncoderProvider, get_encoder_provider
from .jobstore import JobStore, get_job_store
from .llm import LLMProvider, ProviderUnavailable, get_llm_provider
from .storage import StorageProvider, get_storage_provider

__all__ = [
    "Providers",
    "build_providers",
    "LLMProvider",
    "StorageProvider",
    "EncoderProvider",
    "JobStore",
    "ProviderUnavailable",
]


@dataclass
class Providers:
    llm: LLMProvider
    storage: StorageProvider
    encoder: EncoderProvider
    jobstore: JobStore
    report: PreflightReport


def build_providers(config: Config, report: PreflightReport | None = None) -> Providers:
    report = report or run_preflight(config)
    return Providers(
        llm=get_llm_provider(config),
        storage=get_storage_provider(config),
        encoder=get_encoder_provider(report),
        jobstore=get_job_store(config),
        report=report,
    )
