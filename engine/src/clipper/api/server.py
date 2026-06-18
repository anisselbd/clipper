"""Application FastAPI : assemble providers, worker et routes.

Lancement dev :
    uv run uvicorn clipper.api.server:app --reload --port 8008
ou :
    uv run clipper-api
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from ..config import Config
from ..providers import build_providers
from .events import EventBus
from .routes import router
from .worker import JobWorker

logger = logging.getLogger("clipper.api")


@asynccontextmanager
async def lifespan(app: FastAPI):
    config = Config()
    config.ensure_dirs()
    config.data_dir.mkdir(parents=True, exist_ok=True)

    providers = build_providers(config)
    providers.report.log()

    app.state.config = config
    app.state.providers = providers
    app.state.bus = EventBus()
    app.state.worker = JobWorker(config, providers, app.state.bus, concurrency=config.worker_concurrency)
    logger.info("API prete (concurrence=%d).", config.worker_concurrency)
    try:
        yield
    finally:
        app.state.worker.shutdown()


def create_app() -> FastAPI:
    app = FastAPI(title="clipper engine", version="0.1.0", lifespan=lifespan)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[
            "http://localhost:3000", "http://127.0.0.1:3000",
            "http://localhost:1420", "http://127.0.0.1:1420",  # Tauri dev (phase 2)
            "tauri://localhost",
        ],
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(router)
    return app


app = create_app()


def main() -> None:
    """Point d'entree console : lance uvicorn."""
    import uvicorn

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)-7s | %(name)s | %(message)s",
        datefmt="%H:%M:%S",
    )
    for noisy in ("filelock", "huggingface_hub", "fsspec", "httpx", "httpcore"):
        logging.getLogger(noisy).setLevel(logging.WARNING)
    cfg = Config()
    uvicorn.run(app, host=cfg.api_host, port=cfg.api_port, log_level="info")


if __name__ == "__main__":
    main()
