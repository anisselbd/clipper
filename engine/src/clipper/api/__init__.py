"""Couche API (FastAPI) du moteur clipper."""

from __future__ import annotations

from .server import app, create_app, main

__all__ = ["app", "create_app", "main"]
