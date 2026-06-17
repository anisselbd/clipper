"""API HTTP (STUB - phase 2, NON implementee).

Squelette d'une API FastAPI exposant le pipeline. Volontairement non cable au
CLI et non teste. FastAPI n'est pas dans les dependances du MVP : l'import est
protege pour que le module reste lisible/importable sans la dependance.

Pour activer (phase 2) :
    uv add fastapi uvicorn
    uv run uvicorn clipper.api:app --reload
"""

from __future__ import annotations

# TODO (phase 2) : decommenter et implementer une fois `fastapi` ajoute.
#
# from fastapi import BackgroundTasks, FastAPI
# from pydantic import BaseModel
#
# from .config import Config
# from .pipeline import run
#
# app = FastAPI(title="clipper", version="0.1.0")
#
#
# class ProcessRequest(BaseModel):
#     url: str
#     clips: int | None = None
#     lang: str | None = None
#
#
# @app.post("/process")
# def process(req: ProcessRequest, background: BackgroundTasks):
#     """Lance le pipeline sur une URL.
#
#     TODO :
#       - executer `run()` en tache de fond (le pipeline est long et bloquant) ;
#       - renvoyer un job_id et exposer un suivi de progression (SSE/websocket) ;
#       - gerer la concurrence (un seul gros job a la fois sur une machine M4).
#     """
#     config = Config()
#     if req.clips is not None:
#         config.clips = req.clips
#     if req.lang is not None:
#         config.lang = req.lang
#     # background.add_task(run, req.url, config)
#     raise NotImplementedError("POST /process : a implementer en phase 2.")
#
#
# @app.get("/clips")
# def list_clips():
#     """Liste les clips deja generes.
#
#     TODO : lire `output/index.json` et renvoyer la liste des clips + meta,
#     avec une URL statique pour telecharger/preview chaque mp4.
#     """
#     raise NotImplementedError("GET /clips : a implementer en phase 2.")
#
#
# # TODO : monter un StaticFiles sur output/ pour servir les mp4 au front Next.js.

__all__: list[str] = []
