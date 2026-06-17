"""Etape 6 : sous-titres ASS karaoke a partir des timestamps mot a mot.

Style : gros texte gras centre dans le tiers inferieur, mot courant surligne
(couleur d'accent + leger agrandissement) au moment exact ou il est prononce.
Aucune dependance lourde : l'ASS est ecrit a la main.

Les timestamps fournis sont absolus (echelle de la video source) ; ils sont
rebasees sur le debut du clip (t=0) pour coller au flux decoupe au rendu.
"""

from __future__ import annotations

from dataclasses import dataclass

# Couleurs ASS au format &HAABBGGRR (AA=00 -> opaque).
WHITE = "&H00FFFFFF"
ACCENT = "&H0000F2FF"  # jaune/orange vif (R255 G242 B0)
OUTLINE = "&H00000000"  # noir
SHADOW = "&H64000000"  # noir semi-transparent


@dataclass
class WordTiming:
    start: float
    end: float
    text: str


def format_ass_time(seconds: float) -> str:
    """Formate en H:MM:SS.cc (centiseconds) attendu par l'ASS."""
    seconds = max(0.0, seconds)
    cs = int(round(seconds * 100))
    h, cs = divmod(cs, 360000)
    m, cs = divmod(cs, 6000)
    s, cs = divmod(cs, 100)
    return f"{h:d}:{m:02d}:{s:02d}.{cs:02d}"


def _sanitize(text: str) -> str:
    # Les accolades ouvrent les blocs d'override ASS : on les neutralise.
    return text.replace("{", "(").replace("}", ")").replace("\\", "/").strip()


def group_into_lines(
    words: list[WordTiming], max_words: int = 4, max_gap: float = 0.6
) -> list[list[WordTiming]]:
    """Regroupe les mots en lignes courtes (lisibilite verticale).

    Coupe sur : nombre max de mots, pause superieure a max_gap, ou ponctuation
    forte terminant un mot.
    """
    lines: list[list[WordTiming]] = []
    cur: list[WordTiming] = []
    for i, w in enumerate(words):
        if cur:
            gap = w.start - cur[-1].end
            prev = cur[-1].text
            if len(cur) >= max_words or gap > max_gap or prev.endswith((".", "!", "?", "…")):
                lines.append(cur)
                cur = []
        cur.append(w)
    if cur:
        lines.append(cur)
    return lines


def _render_line_events(line: list[WordTiming]) -> list[tuple[float, float, str]]:
    """Un evenement par mot : ligne complete, mot actif surligne."""
    events: list[tuple[float, float, str]] = []
    n = len(line)
    for i, w in enumerate(line):
        ev_start = w.start
        # Continuite : on tient jusqu'au debut du mot suivant (evite le clignotement).
        ev_end = line[i + 1].start if i + 1 < n else w.end
        if ev_end <= ev_start:
            ev_end = ev_start + 0.05
        parts = []
        for j, ww in enumerate(line):
            token = _sanitize(ww.text)
            if j == i:
                parts.append(
                    f"{{\\1c{ACCENT}\\fscx112\\fscy112\\b1}}{token}{{\\r}}"
                )
            else:
                parts.append(token)
        events.append((ev_start, ev_end, " ".join(parts)))
    return events


def build_ass(
    words: list[WordTiming],
    *,
    width: int = 1080,
    height: int = 1920,
    font: str = "Arial",
    font_size: int = 72,
    margin_v: int = 320,
    max_words: int = 4,
) -> str:
    """Construit le contenu complet d'un fichier ASS (timestamps deja clip-locaux)."""
    header = f"""[Script Info]
ScriptType: v4.00+
PlayResX: {width}
PlayResY: {height}
WrapStyle: 0
ScaledBorderAndShadow: yes
YCbCr Matrix: TV.709

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,{font},{font_size},{WHITE},{ACCENT},{OUTLINE},{SHADOW},-1,0,0,0,100,100,0,0,1,5,2,2,90,90,{margin_v},1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    lines = group_into_lines(words, max_words=max_words)
    dialogue: list[str] = []
    for line in lines:
        for start, end, text in _render_line_events(line):
            dialogue.append(
                f"Dialogue: 0,{format_ass_time(start)},{format_ass_time(end)},Default,,0,0,0,,{text}"
            )
    return header + "\n".join(dialogue) + "\n"


def generate_ass_for_clip(
    words_abs: list,
    clip_start: float,
    clip_end: float,
    *,
    width: int = 1080,
    height: int = 1920,
) -> str:
    """Filtre les mots du clip, rebase a t=0 et produit l'ASS.

    `words_abs` : objets ayant .start/.end/.text en temps absolu (Word de
    transcribe). Renvoie le contenu ASS sous forme de chaine.
    """
    local: list[WordTiming] = []
    for w in words_abs:
        mid = (w.start + w.end) / 2.0
        if clip_start <= mid <= clip_end:
            local.append(
                WordTiming(
                    start=max(0.0, w.start - clip_start),
                    end=max(0.05, w.end - clip_start),
                    text=w.text,
                )
            )
    return build_ass(local, width=width, height=height)
