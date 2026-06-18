"""Etape 3 : selection des meilleurs segments.

Le LLM lit le transcript REEL et renvoie des timestamps (selection pure, aucune
invention). Schema de sortie impose :

    [{"start": 12.4, "end": 48.9, "title": "...", "hook_score": 0-100, "reason": "..."}]

Robustesse :
- transcript long (podcast) -> fenetrage temporel, scoring par fenetre, fusion.
- parsing tolerant (fences markdown, texte parasite).
- endpoint LLM injoignable -> bascule sur un fallback heuristique, le pipeline
  reste fonctionnel 100% hors-ligne.
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import asdict, dataclass

from .config import Config
from .providers.llm.client import ProviderUnavailable, build_chat_client
from .transcribe import TSegment, Transcript

logger = logging.getLogger("clipper.segment")

# Sortie structuree (RETEX) : contraint le serveur a renvoyer un tableau JSON
# conforme (converti en grammaire GBNF cote llama.cpp). Degrade en cas de refus.
SEGMENTS_RESPONSE_FORMAT = {
    "type": "json_schema",
    "json_schema": {
        "name": "clip_segments",
        "strict": True,
        "schema": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "start": {"type": "number"},
                    "end": {"type": "number"},
                    "title": {"type": "string"},
                    "hook_score": {"type": "integer", "minimum": 0, "maximum": 100},
                    "reason": {"type": "string"},
                },
                "required": ["start", "end", "title", "hook_score", "reason"],
                "additionalProperties": False,
            },
        },
    },
}

SYSTEM_PROMPT = """\
Tu es un monteur expert en clips verticaux courts (TikTok, Reels, Shorts).
On te donne le transcript reel d'une video, segment par segment, avec des
timestamps en secondes. Ta tache : SELECTIONNER les passages les plus forts.

Regles imperatives :
- Tu ne REFORMULES rien et tu n'INVENTES aucun contenu. Tu choisis uniquement
  des plages temporelles existantes.
- Chaque clip doit etre auto-suffisant et comprehensible seul.
- Privilegie : accroches (hooks), punchlines, prises de position tranchees,
  pics emotionnels, revelations, conseils actionnables.
- Duree cible de chaque clip : entre {min_dur:.0f} et {max_dur:.0f} secondes.
- start et end DOIVENT coincider avec des frontieres de segments fournies
  (debut d'un segment pour start, fin d'un segment pour end), pour ne pas
  couper une phrase au milieu.
- Classe par interet decroissant. Renvoie au plus {n} clips.

Tu reponds UNIQUEMENT avec un tableau JSON valide, sans aucun texte autour,
sans bloc de code markdown. Schema exact de chaque element :
{{"start": <float secondes>, "end": <float secondes>, "title": "<titre court accrocheur>", "hook_score": <entier 0-100>, "reason": "<pourquoi ce passage marche>"}}
"""


@dataclass
class SelectedSegment:
    start: float
    end: float
    title: str
    hook_score: int
    reason: str
    source: str = "llm"  # "llm" ou "heuristic"

    def duration(self) -> float:
        return self.end - self.start


# --------------------------------------------------------------------------- #
# Vue transcript pour le LLM
# --------------------------------------------------------------------------- #

def render_transcript_view(segments: list[TSegment]) -> str:
    """Texte compact : une ligne par segment avec ses bornes temporelles."""
    lines = []
    for s in segments:
        lines.append(f"[{s.start:.1f} -> {s.end:.1f}] {s.text}")
    return "\n".join(lines)


# --------------------------------------------------------------------------- #
# Parsing robuste de la reponse LLM
# --------------------------------------------------------------------------- #

_FENCE_RE = re.compile(r"```(?:json)?\s*(.*?)```", re.DOTALL)


def parse_llm_segments(text: str) -> list[dict]:
    """Extrait un tableau JSON de segments d'une reponse LLM, tolerant au bruit.

    Gere : fences markdown, texte avant/apres, balises <think>.
    Leve ValueError si rien d'exploitable.
    """
    if not text or not text.strip():
        raise ValueError("reponse LLM vide")

    # Retire un eventuel bloc de raisonnement <think>...</think>.
    text = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL)

    candidates: list[str] = []
    # 1) contenu d'un bloc de code markdown
    for m in _FENCE_RE.finditer(text):
        candidates.append(m.group(1))
    # 2) premier tableau JSON equilibre rencontre dans le texte brut
    bracket = _extract_first_array(text)
    if bracket:
        candidates.append(bracket)
    # 3) texte complet en dernier recours
    candidates.append(text)

    for cand in candidates:
        cand = cand.strip()
        if not cand:
            continue
        arr = _extract_first_array(cand) or cand
        try:
            data = json.loads(arr)
        except (json.JSONDecodeError, ValueError):
            continue
        if isinstance(data, dict):
            data = [data]
        if isinstance(data, list):
            return [d for d in data if isinstance(d, dict)]

    raise ValueError("aucun tableau JSON exploitable dans la reponse LLM")


def _extract_first_array(text: str) -> str | None:
    """Renvoie la premiere sous-chaine '[...]' a crochets equilibres."""
    start = text.find("[")
    if start == -1:
        return None
    depth = 0
    in_str = False
    escape = False
    for i in range(start, len(text)):
        ch = text[i]
        if in_str:
            if escape:
                escape = False
            elif ch == "\\":
                escape = True
            elif ch == '"':
                in_str = False
            continue
        if ch == '"':
            in_str = True
        elif ch == "[":
            depth += 1
        elif ch == "]":
            depth -= 1
            if depth == 0:
                return text[start : i + 1]
    return None


# --------------------------------------------------------------------------- #
# Alignement sur frontieres de phrase + validation
# --------------------------------------------------------------------------- #

def snap_to_boundaries(
    start: float, end: float, segments: list[TSegment]
) -> tuple[float, float]:
    """Aligne (start, end) sur les frontieres de segments Whisper les plus proches."""
    starts = [s.start for s in segments]
    ends = [s.end for s in segments]
    # start : derniere frontiere de debut <= start (sinon la plus proche).
    le_starts = [b for b in starts if b <= start + 0.25]
    new_start = max(le_starts) if le_starts else min(starts, key=lambda b: abs(b - start))
    # end : premiere frontiere de fin >= end (sinon la plus proche).
    ge_ends = [b for b in ends if b >= end - 0.25]
    new_end = min(ge_ends) if ge_ends else min(ends, key=lambda b: abs(b - end))
    if new_end <= new_start:
        new_end = end if end > new_start else new_start + 1.0
    return new_start, new_end


def _enforce_duration(
    start: float, end: float, segments: list[TSegment], min_dur: float, max_dur: float
) -> tuple[float, float]:
    ends = sorted(s.end for s in segments)
    # Trop long : ramener end a la derniere frontiere <= start+max_dur.
    if end - start > max_dur:
        cap = start + max_dur
        valid = [e for e in ends if start < e <= cap]
        end = max(valid) if valid else cap
    # Trop court : etendre end vers la prochaine frontiere jusqu'a >= min_dur.
    if end - start < min_dur:
        for e in ends:
            if e > end:
                end = e
                if end - start >= min_dur:
                    break
    return start, end


def validate_segments(
    raw: list[dict],
    transcript: Transcript,
    *,
    min_dur: float,
    max_dur: float,
    source: str = "llm",
) -> list[SelectedSegment]:
    segments = transcript.segments
    out: list[SelectedSegment] = []
    for item in raw:
        try:
            start = float(item["start"])
            end = float(item["end"])
        except (KeyError, TypeError, ValueError):
            continue
        if end <= start:
            continue
        start = max(0.0, min(start, transcript.duration))
        end = max(0.0, min(end, transcript.duration))
        if segments:
            start, end = snap_to_boundaries(start, end, segments)
            start, end = _enforce_duration(start, end, segments, min_dur, max_dur)
        if end - start < 1.0:
            continue
        score = item.get("hook_score", 50)
        try:
            score = int(round(float(score)))
        except (TypeError, ValueError):
            score = 50
        out.append(
            SelectedSegment(
                start=round(start, 2),
                end=round(end, 2),
                title=str(item.get("title") or "Sans titre").strip()[:120],
                hook_score=max(0, min(100, score)),
                reason=str(item.get("reason") or "").strip()[:400],
                source=source,
            )
        )
    return out


def dedup_and_rank(segments: list[SelectedSegment], n: int) -> list[SelectedSegment]:
    """Trie par score puis ecarte les chevauchements (>50%), garde le top n."""
    ranked = sorted(segments, key=lambda s: s.hook_score, reverse=True)
    kept: list[SelectedSegment] = []
    for cand in ranked:
        overlap = False
        for k in kept:
            inter = max(0.0, min(cand.end, k.end) - max(cand.start, k.start))
            shorter = min(cand.duration(), k.duration())
            if shorter > 0 and inter / shorter > 0.5:
                overlap = True
                break
        if not overlap:
            kept.append(cand)
        if len(kept) >= n:
            break
    kept.sort(key=lambda s: s.start)
    return kept


# --------------------------------------------------------------------------- #
# Fenetrage (transcripts longs)
# --------------------------------------------------------------------------- #

def _windows(segments: list[TSegment], window_s: float = 540.0) -> list[list[TSegment]]:
    """Decoupe les segments en fenetres temporelles d'environ window_s secondes."""
    if not segments:
        return []
    windows: list[list[TSegment]] = []
    cur: list[TSegment] = []
    w_start = segments[0].start
    for s in segments:
        if cur and s.end - w_start > window_s:
            windows.append(cur)
            cur = []
            w_start = s.start
        cur.append(s)
    if cur:
        windows.append(cur)
    return windows


# --------------------------------------------------------------------------- #
# Selection heuristique (fallback hors-ligne)
# --------------------------------------------------------------------------- #

_STRONG = re.compile(
    r"\b(jamais|toujours|secret|erreur|incroyable|important|attention|"
    r"argent|reussir|echec|peur|verite|probleme|solution|astuce|pourquoi|"
    r"comment|million|gratuit)\b",
    re.IGNORECASE,
)


def heuristic_select(
    transcript: Transcript, *, n: int, min_dur: float, max_dur: float
) -> list[SelectedSegment]:
    """Selection sans LLM : fenetres glissantes scorees sur des signaux simples.

    Signaux : presence de '?'/'!', mots forts, densite de parole. Suffisant pour
    faire tourner le pipeline de bout en bout hors-ligne ; le LLM fait mieux.
    """
    segments = transcript.segments
    if not segments:
        return []

    candidates: list[SelectedSegment] = []
    for i in range(len(segments)):
        start = segments[i].start
        j = i
        text_parts: list[str] = []
        while j < len(segments) and segments[j].end - start < min_dur:
            text_parts.append(segments[j].text)
            j += 1
        if j >= len(segments):
            break
        # etend jusqu'a une fin de phrase dans [min_dur, max_dur]
        end = segments[j].end if segments[j].end - start <= max_dur else start + max_dur
        text_parts.append(segments[j].text)
        text = " ".join(text_parts)

        dur = max(1.0, end - start)
        words = sum(len(s.words) for s in segments[i : j + 1])
        density = words / dur
        score = (
            text.count("?") * 12
            + text.count("!") * 8
            + len(_STRONG.findall(text)) * 6
            + min(density * 4.0, 30.0)
        )
        candidates.append(
            SelectedSegment(
                start=round(start, 2),
                end=round(end, 2),
                title=_make_title(text),
                hook_score=int(min(100, 30 + score)),
                reason="Selection heuristique (LLM indisponible) : densite et marqueurs d'accroche.",
                source="heuristic",
            )
        )

    return dedup_and_rank(candidates, n)


def _make_title(text: str) -> str:
    words = text.split()
    title = " ".join(words[:8])
    return (title[:80] + "...") if len(title) > 80 else title


# --------------------------------------------------------------------------- #
# Point d'entree
# --------------------------------------------------------------------------- #

def _complete_window(provider, system: str, user: str, use_schema: list[bool]) -> str:
    """Appel LLM avec sortie structuree, degradation gracieuse si refusee."""
    rf = SEGMENTS_RESPONSE_FORMAT if use_schema[0] else None
    try:
        return provider.complete(system, user, temperature=0.0, max_tokens=2048, response_format=rf)
    except ProviderUnavailable:
        if rf is not None:
            # Le serveur ne supporte peut-etre pas response_format : on reessaie sans.
            use_schema[0] = False
            logger.warning("response_format refuse/indisponible, bascule sans schema structure.")
            return provider.complete(system, user, temperature=0.0, max_tokens=2048, response_format=None)
        raise


def select_segments(transcript: Transcript, config: Config) -> list[SelectedSegment]:
    """Renvoie au plus config.clips segments, via LLM puis fallback heuristique."""
    n = config.clips
    min_dur, max_dur = config.min_duration, config.max_duration

    if not transcript.segments:
        logger.warning("Transcript vide : aucune selection possible.")
        return []

    provider = build_chat_client(config)
    system = SYSTEM_PROMPT.format(min_dur=min_dur, max_dur=max_dur, n=n)

    retries = max(1, config.llm_retries)
    # Sortie structuree activable ; desactivee a la volee si le serveur la refuse.
    use_schema = [bool(config.llm_structured_output)]
    try:
        collected: list[SelectedSegment] = []
        windows = _windows(transcript.segments)
        logger.info("Selection LLM (%s) sur %d fenetre(s)...", provider.name, len(windows))
        for wi, win in enumerate(windows):
            view = render_transcript_view(win)
            user = (
                "Transcript (timestamps en secondes) :\n\n"
                f"{view}\n\n"
                f"Selectionne les meilleurs clips ({min_dur:.0f}-{max_dur:.0f}s). "
                "Reponds uniquement avec le tableau JSON."
            )
            # Temperature 0 (deterministe, meilleur suivi du format) + reessais
            # si la reponse n'est pas un JSON exploitable.
            raw: list[dict] | None = None
            for attempt in range(retries):
                raw_text = _complete_window(provider, system, user, use_schema)
                try:
                    parsed = parse_llm_segments(raw_text)
                except ValueError:
                    parsed = []
                if parsed:
                    raw = parsed
                    break
                logger.warning(
                    "Fenetre %d : reponse LLM non exploitable (essai %d/%d).",
                    wi + 1, attempt + 1, retries,
                )
            if raw:
                collected.extend(
                    validate_segments(
                        raw, transcript, min_dur=min_dur, max_dur=max_dur, source="llm"
                    )
                )
        selected = dedup_and_rank(collected, n)
        if selected:
            logger.info("Selection LLM : %d clip(s) retenu(s).", len(selected))
            return selected
        logger.warning("Le LLM n'a renvoye aucun segment valide, bascule heuristique.")
    except ProviderUnavailable as exc:
        logger.warning("LLM indisponible (%s). Bascule sur le fallback heuristique.", exc)

    selected = heuristic_select(transcript, n=n, min_dur=min_dur, max_dur=max_dur)
    logger.info("Selection heuristique : %d clip(s).", len(selected))
    return selected


def segments_to_dicts(segments: list[SelectedSegment]) -> list[dict]:
    return [asdict(s) for s in segments]
