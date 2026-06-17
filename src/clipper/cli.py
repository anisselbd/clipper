"""Point d'entree CLI : `clipper <url>`."""

from __future__ import annotations

import argparse
import logging
import sys

from .config import Config
from .pipeline import run


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="clipper",
        description="Genere des clips verticaux 9:16 sous-titres a partir d'une URL video.",
    )
    p.add_argument("url", help="URL de la video source (YouTube en priorite).")
    p.add_argument("--clips", type=int, default=None, help="Nombre de clips a produire (defaut 8).")
    p.add_argument("--lang", default=None, help="Code langue de la transcription (defaut fr).")
    p.add_argument(
        "--whisper-model",
        default=None,
        help="Modele faster-whisper : tiny/base/small/medium/large-v3 (defaut small).",
    )
    p.add_argument("--provider", default=None, help="Fournisseur LLM : local_llm (defaut) ou anthropic.")
    p.add_argument("--output", default=None, help="Repertoire de sortie (defaut output/).")
    p.add_argument("-v", "--verbose", action="store_true", help="Logs detailles (DEBUG).")
    return p


def _make_config(args: argparse.Namespace) -> Config:
    config = Config()
    if args.clips is not None:
        config.clips = args.clips
    if args.lang is not None:
        config.lang = args.lang
    if args.whisper_model is not None:
        config.whisper_model = args.whisper_model
    if args.provider is not None:
        config.llm_provider = args.provider
    if args.output is not None:
        from pathlib import Path

        config.output_dir = Path(args.output)
    return config


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s | %(levelname)-7s | %(name)s | %(message)s",
        datefmt="%H:%M:%S",
    )
    # Bride le bruit des dependances tierces.
    for noisy in ("urllib3", "httpx", "httpcore"):
        logging.getLogger(noisy).setLevel(logging.WARNING)

    config = _make_config(args)
    try:
        index = run(args.url, config)
    except KeyboardInterrupt:
        print("\nInterrompu.", file=sys.stderr)
        return 130
    except Exception as exc:  # noqa: BLE001
        logging.getLogger("clipper").exception("Echec du pipeline : %s", exc)
        return 1

    n = index.get("clip_count", 0)
    print(f"\n{n} clip(s) genere(s) -> {config.output_dir}/index.json")
    return 0 if n > 0 else 2


if __name__ == "__main__":
    raise SystemExit(main())
