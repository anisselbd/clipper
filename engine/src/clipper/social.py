"""Etape post-production : kit social pret-a-poster par clip.

Pour chaque clip, on genere une accroche (caption), un titre court YouTube et
des hashtags pertinents, puis on assemble des variantes par plateforme
(TikTok / YouTube Shorts / Instagram Reels). Objectif : l'utilisateur n'a plus
qu'a uploader le mp4 et coller la legende.

Generation par LLM (un appel batche, sortie structuree) avec fallback
heuristique hors-ligne. Le LLM SELECTIONNE/RESUME le contenu reel, il n'invente
pas de faits.
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field

from .config import Config
from .providers.llm.client import ProviderUnavailable, build_chat_client
from .segment import parse_llm_segments  # parsing JSON tolerant reutilise

logger = logging.getLogger("clipper.social")

# Tags propres a chaque plateforme, ajoutes en plus des hashtags de contenu.
PLATFORM_TAGS = {
    "tiktok": ["#fyp", "#pourtoi"],
    "shorts": ["#shorts"],
    "reels": ["#reels"],
}

SOCIAL_SYSTEM = """\
Tu es un expert du copywriting pour clips verticaux courts (TikTok, YouTube
Shorts, Instagram Reels). On te donne une liste de clips, chacun avec un titre
et un extrait du transcript reel.

IMPORTANT : ecris TOUT le texte (caption ET youtube_title) en {lang_name} ({lang}),
quelle que soit la langue du transcript. C'est imperatif.

Pour CHAQUE clip, ecris :
- "caption" : une accroche courte et percutante (1 a 2 phrases) en {lang_name},
  pensee pour stopper le scroll. Un emoji max, pas de hashtags ici.
- "youtube_title" : un titre court et accrocheur pour YouTube Shorts (en {lang_name}).
- "hashtags" : 5 a 8 hashtags pertinents lies au CONTENU (sujet, noms, theme).
  N'inclus PAS #fyp, #shorts, #reels (ajoutes automatiquement).

Tu ne mens pas et n'inventes aucun fait : tu t'appuies sur le contenu fourni.
Reponds UNIQUEMENT avec un tableau JSON, un objet par clip, dans l'ordre :
{{"clip_id": "...", "caption": "...", "youtube_title": "...", "hashtags": ["#..."]}}
"""

SOCIAL_RESPONSE_FORMAT = {
    "type": "json_schema",
    "json_schema": {
        "name": "social_kits",
        "strict": True,
        "schema": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "clip_id": {"type": "string"},
                    "caption": {"type": "string"},
                    "youtube_title": {"type": "string"},
                    "hashtags": {"type": "array", "items": {"type": "string"}},
                },
                "required": ["clip_id", "caption", "youtube_title", "hashtags"],
                "additionalProperties": False,
            },
        },
    },
}


@dataclass
class SocialKit:
    clip_id: str
    caption: str
    youtube_title: str
    hashtags: list[str] = field(default_factory=list)
    source: str = "llm"  # "llm" ou "heuristic"

    def for_platform(self, platform: str) -> dict:
        """Rend le texte pret a coller pour une plateforme donnee."""
        tags = self.hashtags + PLATFORM_TAGS.get(platform, [])
        tagline = " ".join(tags)
        if platform == "shorts":
            return {
                "title": (self.youtube_title or self.caption)[:100],
                "description": f"{self.caption}\n\n{tagline}".strip(),
            }
        # tiktok / reels : une seule legende
        return {"caption": f"{self.caption}\n\n{tagline}".strip()}

    def as_dict(self) -> dict:
        return {
            "clip_id": self.clip_id,
            "caption": self.caption,
            "youtube_title": self.youtube_title,
            "hashtags": self.hashtags,
            "source": self.source,
            "platforms": {p: self.for_platform(p) for p in PLATFORM_TAGS},
        }

    def to_post_text(self) -> str:
        """Fichier post.txt lisible, pret a copier-coller."""
        tt = self.for_platform("tiktok")["caption"]
        rl = self.for_platform("reels")["caption"]
        yt = self.for_platform("shorts")
        return (
            f"# {self.youtube_title}\n\n"
            f"== TikTok ==\n{tt}\n\n"
            f"== Instagram Reels ==\n{rl}\n\n"
            f"== YouTube Shorts ==\nTitre : {yt['title']}\n{yt['description']}\n"
        )


def _normalize_hashtags(tags: list[str], extra_from: str = "") -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for t in tags:
        t = t.strip()
        if not t:
            continue
        if not t.startswith("#"):
            t = "#" + re.sub(r"[^0-9A-Za-zÀ-ÿ]+", "", t)
        key = t.lower()
        if len(t) > 1 and key not in seen:
            seen.add(key)
            out.append(t)
    return out[:8]


# --------------------------------------------------------------------------- #
# Fallback heuristique
# --------------------------------------------------------------------------- #

_SPORT = re.compile(r"\b(goal|but|gol|messi|penalty|score|match|cup|league|football|soccer)\b", re.IGNORECASE)
_STOP = set("the a an of to and in on for with is are was were this that les des une est que qui pour dans avec sur".split())


def _keyword_hashtags(text: str, n: int = 6) -> list[str]:
    words = re.findall(r"[0-9A-Za-zÀ-ÿ]{3,}", text.lower())
    freq: dict[str, int] = {}
    for w in words:
        if w in _STOP:
            continue
        freq[w] = freq.get(w, 0) + 1
    top = sorted(freq, key=lambda w: freq[w], reverse=True)[:n]
    return ["#" + w for w in top]


def _heuristic_kit(clip: dict) -> SocialKit:
    title = clip.get("title") or "Clip"
    text = clip.get("text") or ""
    is_sport = bool(_SPORT.search(title + " " + text))
    base = ["#football", "#sport", "#highlights"] if is_sport else ["#clip", "#viral"]
    tags = _normalize_hashtags(base + _keyword_hashtags(title))
    return SocialKit(
        clip_id=clip["clip_id"],
        caption=title if title.endswith(("!", "?", ".")) else title + " 🔥",
        youtube_title=title[:100],
        hashtags=tags,
        source="heuristic",
    )


def _heuristic_kits(clips: list[dict]) -> list[SocialKit]:
    return [_heuristic_kit(c) for c in clips]


# --------------------------------------------------------------------------- #
# Point d'entree
# --------------------------------------------------------------------------- #

def generate_social_kits(clips: list[dict], config: Config) -> list[SocialKit]:
    """clips : [{clip_id, title, text}]. Renvoie un SocialKit par clip."""
    if not clips:
        return []

    lang_names = {"fr": "francais", "en": "anglais", "es": "espagnol", "de": "allemand", "it": "italien", "pt": "portugais"}
    provider = build_chat_client(config)
    system = SOCIAL_SYSTEM.format(lang=config.lang, lang_name=lang_names.get(config.lang, config.lang))
    payload = [
        {"clip_id": c["clip_id"], "title": c.get("title", ""), "text": (c.get("text") or "")[:600]}
        for c in clips
    ]
    user = (
        "Clips :\n\n"
        + json.dumps(payload, ensure_ascii=False, indent=1)
        + "\n\nEcris le kit social de chaque clip. Reponds uniquement avec le tableau JSON."
    )

    use_schema = bool(config.llm_structured_output)
    try:
        rf = SOCIAL_RESPONSE_FORMAT if use_schema else None
        try:
            raw_text = provider.complete(system, user, temperature=0.3, max_tokens=2048, response_format=rf)
        except ProviderUnavailable:
            if rf is None:
                raise
            raw_text = provider.complete(system, user, temperature=0.3, max_tokens=2048, response_format=None)

        raw = parse_llm_segments(raw_text)  # parse tolerant d'un tableau JSON
        by_id = {str(r.get("clip_id")): r for r in raw if isinstance(r, dict)}
        kits: list[SocialKit] = []
        for c in clips:
            r = by_id.get(c["clip_id"])
            if not r or not r.get("caption"):
                kits.append(_heuristic_kit(c))
                continue
            kits.append(
                SocialKit(
                    clip_id=c["clip_id"],
                    caption=str(r.get("caption", "")).strip()[:300],
                    youtube_title=str(r.get("youtube_title") or c.get("title", "")).strip()[:100],
                    hashtags=_normalize_hashtags(list(r.get("hashtags") or [])) or _heuristic_kit(c).hashtags,
                    source="llm",
                )
            )
        logger.info("Kits sociaux : %d (LLM).", len(kits))
        return kits
    except (ProviderUnavailable, ValueError) as exc:
        logger.warning("Copy LLM indisponible (%s). Fallback heuristique.", exc)
        return _heuristic_kits(clips)
