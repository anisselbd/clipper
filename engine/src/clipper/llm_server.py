"""Auto-gestion d'un petit LLM local pour rendre l'app autonome.

Si aucun LLM n'est joignable, le moteur telecharge une fois un petit modele
(GGUF ~2 Go) et lance son propre llama-server, l'utilise, et l'arrete a la
fermeture. Si un LLM repond deja sur LLM_BASE_URL (gros modele lance a la main),
il est prefere et rien n'est demarre.
"""

from __future__ import annotations

import logging
import os
import subprocess
import time
from pathlib import Path

logger = logging.getLogger("clipper.llm_server")

# Handle global du llama-server gere (un seul par process).
_managed: dict[str, subprocess.Popen | None] = {"proc": None}


def _reachable(base_url: str, timeout: float = 2.0) -> bool:
    try:
        import httpx

        r = httpx.get(f"{base_url.rstrip('/')}/models", timeout=timeout)
        return r.status_code < 500
    except Exception:
        return False


def ensure_model(config) -> Path | None:
    """Garantit la presence du petit modele ; le telecharge une fois si besoin."""
    models_dir = config.models_dir
    models_dir.mkdir(parents=True, exist_ok=True)
    name = config.llm_autostart_model_url.rsplit("/", 1)[-1]
    path = models_dir / name
    if path.exists() and path.stat().st_size > 100_000_000:  # garde-fou : >100 Mo
        return path
    tmp = path.with_suffix(".part")
    try:
        import httpx

        logger.info("Telechargement du modele LLM leger (une seule fois)...")
        with httpx.stream("GET", config.llm_autostart_model_url, timeout=None, follow_redirects=True) as r:
            r.raise_for_status()
            with open(tmp, "wb") as fh:
                for chunk in r.iter_bytes(1 << 20):
                    fh.write(chunk)
        tmp.rename(path)
        logger.info("Modele LLM pret : %s (%.1f Go).", name, path.stat().st_size / 1e9)
        return path
    except Exception as exc:
        logger.warning("Echec du telechargement du modele LLM (%s).", exc)
        tmp.unlink(missing_ok=True)
        return None


def _enriched_env() -> dict:
    env = dict(os.environ)
    extra = "/opt/homebrew/bin:/Users/anisse/.local/bin"
    env["PATH"] = extra + ":" + env.get("PATH", "/usr/bin:/bin")
    return env


def ensure_local_llm(config) -> str:
    """Renvoie le base_url LLM effectif, en demarrant un serveur local si besoin.

    Mutation conseillee par l'appelant : config.llm_base_url = ensure_local_llm(config).
    """
    if _reachable(config.llm_base_url):
        logger.info("LLM deja joignable sur %s (prefere).", config.llm_base_url)
        return config.llm_base_url
    if not config.llm_autostart:
        return config.llm_base_url

    model = ensure_model(config)
    if model is None:
        return config.llm_base_url

    port = config.llm_autostart_port
    cmd = [
        config.llm_server_bin, "-m", str(model),
        "--host", "127.0.0.1", "--port", str(port),
        "-c", "8192", "-ngl", "99", "--jinja",
    ]
    try:
        proc = subprocess.Popen(
            cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, env=_enriched_env()
        )
    except FileNotFoundError:
        logger.warning("llama-server introuvable (%s) : selection heuristique.", config.llm_server_bin)
        return config.llm_base_url

    _managed["proc"] = proc
    base = f"http://127.0.0.1:{port}/v1"
    logger.info("Demarrage du LLM local (%s) sur %s...", model.name, base)
    for _ in range(180):
        if _reachable(base):
            logger.info("LLM local pret.")
            return base
        if proc.poll() is not None:
            logger.warning("Le LLM local s'est arrete prematurement.")
            _managed["proc"] = None
            return config.llm_base_url
        time.sleep(1.0)
    logger.warning("LLM local pas pret a temps (on tentera quand meme).")
    return base


def stop_local_llm() -> None:
    proc = _managed.get("proc")
    if proc is None:
        return
    _managed["proc"] = None
    try:
        proc.terminate()
        proc.wait(timeout=5)
    except Exception:
        try:
            proc.kill()
        except Exception:
            pass
    logger.info("LLM local arrete.")
