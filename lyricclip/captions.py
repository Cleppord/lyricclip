"""Build an .ass subtitle file (burned in by ffmpeg/libass) from timed lyrics."""
from __future__ import annotations

from .lyrics import Line, LyricsFile

W, H = 1080, 1920

STYLES = ("karaoke", "pop", "lines")


def _ass_time(t: float) -> str:
    t = max(0.0, t)
    cs = int(round(t * 100))
    h, cs = divmod(cs, 360000)
    m, cs = divmod(cs, 6000)
    s, cs = divmod(cs, 100)
    return f"{h}:{m:02d}:{s:02d}.{cs:02d}"


def _esc(s: str) -> str:
    return s.replace("\\", "\\\\").replace("{", "(").replace("}", ")")


def _clip_lines(lf: LyricsFile, lead_in: float = 0.12, hold: float = 0.45) -> list[Line]:
    """Shift lines into clip time, drop ones outside, and close tiny gaps to avoid flicker."""
    start, length = lf.clip_start, lf.clip_length
    out = []
    for ln in lf.lines:
        s, e = ln.start - start, ln.end - start
        if e <= 0 or s >= length:
            continue
        words = [type(w)(w.text, w.start - start, w.end - start) for w in ln.words]
        out.append(Line(s, e, ln.text, words))
    for i, ln in enumerate(out):
        nxt = out[i + 1].start - lead_in if i + 1 < len(out) else length
        # linger a moment after the last word, but never overlap the next line
        ln.end = min(ln.end + hold, max(nxt, ln.start + 0.2))
        ln.start = max(0.0, ln.start - lead_in)
        ln.end = min(ln.end, length)
    return out


def build_ass(lf: LyricsFile, style: str = "karaoke", font: str = "Arial",
              uppercase: bool = False, font_size: int | None = None,
              highlight: str = "&H0000E1FF", y_pos: int = 1180) -> str:
    """Return the full text of an .ass file. Colours are ASS &HAABBGGRR (default: gold)."""
    if style not in STYLES:
        raise ValueError(f"style must be one of {STYLES}")
    size = font_size or (118 if style == "pop" else 86)
    margin_v = H - y_pos
    # Primary = sung/highlight colour, Secondary = not-yet-sung (karaoke \k fills Secondary→Primary)
    primary, secondary = (highlight, "&H00FFFFFF") if style == "karaoke" else ("&H00FFFFFF", "&H00FFFFFF")
    head = f"""[Script Info]
ScriptType: v4.00+
PlayResX: {W}
PlayResY: {H}
WrapStyle: 0
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Lyric,{font},{size},{primary},{secondary},&H00000000,&H96000000,-1,0,0,0,100,100,0,0,1,7,3,2,90,90,{margin_v},1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    events = []

    def word_text(t: str) -> str:
        return _esc(t.upper() if uppercase else t)

    for ln in _clip_lines(lf):
        if style == "lines":
            events.append((ln.start, ln.end, r"{\fad(120,120)}" + word_text(ln.text)))
        elif style == "karaoke":
            parts, cursor = [r"{\fad(100,100)}"], ln.start
            for w in ln.words:
                ws = max(w.start, cursor)
                if ws > cursor:  # silence before this word
                    parts.append(f"{{\\k{int(round((ws - cursor) * 100))}}}")
                dur = max(0.0, max(w.end, ws) - ws)
                parts.append(f"{{\\k{int(round(dur * 100))}}}{word_text(w.text)} ")
                cursor = ws + dur
            events.append((ln.start, ln.end, "".join(parts).rstrip()))
        else:  # pop: 1–3 words at a time, punching in
            groups, cur = [], []
            for w in ln.words:
                cur.append(w)
                if len(cur) >= 3 or w.text[-1:] in ",.!?" or len(" ".join(x.text for x in cur)) > 14:
                    groups.append(cur)
                    cur = []
            if cur:
                groups.append(cur)
            for gi, g in enumerate(groups):
                gs = max(0.0, g[0].start)
                ge = groups[gi + 1][0].start if gi + 1 < len(groups) else ln.end
                if ge - gs < 0.08:
                    continue
                txt = " ".join(word_text(w.text) for w in g)
                anim = r"{\fscx70\fscy70\t(0,90,\fscx108\fscy108)\t(90,160,\fscx100\fscy100)}"
                events.append((gs, ge, anim + txt))

    body = "".join(f"Dialogue: 0,{_ass_time(s)},{_ass_time(e)},Lyric,,0,0,0,,{t}\n"
                   for s, e, t in events if e > s)
    return head + body
