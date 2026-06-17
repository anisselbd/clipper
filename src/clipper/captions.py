"""Etape 6 : sous-titres karaoke a partir des timestamps mot a mot.

Deux chemins de rendu, choisis par render.py selon les capacites de ffmpeg :

1. ASS (libass) : style gros texte gras centre dans le tiers inferieur, mot
   courant surligne, ecrit a la main. Chemin canonique si ffmpeg embarque
   libass.
2. Overlay Pillow : si ffmpeg n'a PAS libass, on rend chaque etat (ligne + mot
   actif) en PNG transparent avec Pillow, puis on les incruste via le
   demultiplexeur `concat` + le filtre `overlay` (coeur de ffmpeg). 100%
   hors-ligne, aucune dependance systeme.

Les timestamps fournis sont absolus (echelle de la video source) ; ils sont
rebasees sur le debut du clip (t=0) pour coller au flux decoupe au rendu.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

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


# --------------------------------------------------------------------------- #
# Chemin de rendu alternatif : overlay PNG via Pillow (ffmpeg sans libass)
# --------------------------------------------------------------------------- #

# Couleurs RGBA pour Pillow.
WHITE_RGB = (255, 255, 255, 255)
ACCENT_RGB = (255, 214, 10, 255)  # jaune dore
STROKE_RGB = (0, 0, 0, 255)
TRANSPARENT = (0, 0, 0, 0)

_FONT_CANDIDATES = [
    "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
    "/System/Library/Fonts/Supplemental/Arial.ttf",
    "/System/Library/Fonts/HelveticaNeue.ttc",
    "/System/Library/Fonts/Helvetica.ttc",
    "/System/Library/Fonts/SFNS.ttf",
]


def _resolve_font_path(font_path: str | None) -> str | None:
    if font_path and Path(font_path).exists():
        return font_path
    for cand in _FONT_CANDIDATES:
        if Path(cand).exists():
            return cand
    return None


def _load_font(font_path: str | None, size: int):
    from PIL import ImageFont

    resolved = _resolve_font_path(font_path)
    if resolved:
        try:
            return ImageFont.truetype(resolved, size)
        except Exception:
            pass
    return ImageFont.load_default(size)


@dataclass
class _Event:
    start: float
    end: float
    words: list[str]
    active: int  # index du mot surligne, -1 si vide (silence)


def build_overlay_events(words: list[WordTiming], clip_dur: float, max_words: int = 4) -> list[_Event]:
    """Construit la timeline complete d'evenements couvrant [0, clip_dur].

    Un evenement par mot prononce (ligne affichee, mot actif surligne), avec
    des trous transparents pour les silences.
    """
    events: list[_Event] = []
    cursor = 0.0
    for line in group_into_lines(words, max_words=max_words):
        texts = [w.text for w in line]
        n = len(line)
        for i, w in enumerate(line):
            start = max(cursor, w.start)
            end = line[i + 1].start if i + 1 < n else w.end
            if end <= start:
                end = start + 0.05
            if start - cursor > 0.04:
                events.append(_Event(cursor, start, [], -1))  # silence
            events.append(_Event(start, end, texts, i))
            cursor = end
    if clip_dur - cursor > 0.04:
        events.append(_Event(cursor, clip_dur, [], -1))
    return events


def _draw_event(img_size, words: list[str], active: int, font, draw_y: int):
    """Dessine une ligne centree, mot actif en couleur d'accent (sans jitter)."""
    from PIL import Image, ImageDraw

    width, height = img_size
    img = Image.new("RGBA", img_size, TRANSPARENT)
    if not words:
        return img
    draw = ImageDraw.Draw(img)

    space = font.getlength(" ")
    widths = [font.getlength(w) for w in words]
    total = sum(widths) + space * (len(words) - 1)
    usable = width * 0.92
    fnt = font
    if total > usable and total > 0:
        # Reduit la police pour faire tenir la ligne.
        scale = usable / total
        fnt = _load_font(None, max(28, int(font.size * scale)))
        space = fnt.getlength(" ")
        widths = [fnt.getlength(w) for w in words]
        total = sum(widths) + space * (len(words) - 1)

    stroke = max(4, fnt.size // 12)
    x = (width - total) / 2.0
    for i, word in enumerate(words):
        color = ACCENT_RGB if i == active else WHITE_RGB
        draw.text(
            (x, draw_y),
            word,
            font=fnt,
            fill=color,
            anchor="lm",
            stroke_width=stroke,
            stroke_fill=STROKE_RGB,
        )
        x += widths[i] + space
    return img


def render_overlay_assets(
    words_abs: list,
    clip_start: float,
    clip_end: float,
    out_dir: Path,
    *,
    width: int = 1080,
    height: int = 1920,
    font_path: str | None = None,
    font_size: int = 76,
) -> Path | None:
    """Rend les PNG des sous-titres et un script concat ffmpeg.

    Renvoie le chemin du fichier concat (ffconcat), ou None si aucun mot.
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
    if not local:
        return None

    clip_dur = clip_end - clip_start
    events = build_overlay_events(local, clip_dur)

    out_dir.mkdir(parents=True, exist_ok=True)
    font = _load_font(font_path, font_size)
    draw_y = int(height * 0.74)

    # PNG transparent partage pour tous les silences.
    from PIL import Image

    transparent_path = out_dir / "blank.png"
    Image.new("RGBA", (width, height), TRANSPARENT).save(transparent_path)

    entries: list[tuple[Path, float]] = []
    for idx, ev in enumerate(events):
        dur = max(0.04, ev.end - ev.start)
        if ev.active < 0 or not ev.words:
            entries.append((transparent_path, dur))
            continue
        img = _draw_event((width, height), ev.words, ev.active, font, draw_y)
        png = out_dir / f"ev_{idx:04d}.png"
        img.save(png)
        entries.append((png, dur))

    # Ecrit le script concat (chemins absolus, dernier fichier repete pour
    # appliquer sa duree, quirk du demultiplexeur concat).
    list_path = out_dir / "concat.txt"
    lines = ["ffconcat version 1.0"]
    for png, dur in entries:
        lines.append(f"file '{png.resolve()}'")
        lines.append(f"duration {dur:.3f}")
    if entries:
        lines.append(f"file '{entries[-1][0].resolve()}'")
    list_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return list_path
