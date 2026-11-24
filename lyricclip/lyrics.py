"""The editable lyrics file format, plus word-timing bookkeeping.

A lyrics file looks like this (times are positions in the FULL song):

    clip_start = 42.50
    clip_length = 15

    [00:42.80 --> 00:45.10] I been running all night
    [00:45.30 --> 00:47.90] city lights in my eyes

Fix typos, retime lines, add or delete lines, or change clip_start to use a
different part of the song. Lines starting with # are comments.
"""
from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass, field
from pathlib import Path


@dataclass
class Word:
    text: str
    start: float
    end: float


@dataclass
class Line:
    start: float
    end: float
    text: str
    words: list[Word] = field(default_factory=list)


@dataclass
class LyricsFile:
    lines: list[Line]
    clip_start: float = 0.0
    clip_length: float = 15.0


HEADER = """\
# lyricclip lyrics file — edit anything below, then render.
#   * Fix wrong words just by retyping them.
#   * Each line is  [start --> end] text   (mm:ss.cc in the FULL song; plain seconds also work)
#   * Add or delete lines freely. Lines starting with # are ignored.
#   * clip_start picks which part of the song the video uses (seconds).
"""

_TIMED = re.compile(r"^\[\s*([\d:.]+)\s*(?:-->|-)\s*([\d:.]+)\s*\]\s*(.*)$")
_SETTING = re.compile(r"^(\w+)\s*=\s*([\d.]+)\s*$")


def fmt_time(t: float) -> str:
    t = max(0.0, t)
    m, s = divmod(t, 60)
    return f"{int(m):02d}:{s:05.2f}"


def parse_time(s: str) -> float:
    parts = s.split(":")
    secs = 0.0
    for p in parts:
        secs = secs * 60 + float(p)
    return secs


def words_to_lines(words: list[Word], max_words: int = 7, max_gap: float = 0.7,
                   max_dur: float = 4.5) -> list[Line]:
    """Group transcribed words into short, caption-sized lines."""
    lines: list[Line] = []
    cur: list[Word] = []

    def flush():
        if cur:
            lines.append(Line(cur[0].start, cur[-1].end,
                              " ".join(w.text for w in cur), list(cur)))
            cur.clear()

    for w in words:
        if cur:
            gap = w.start - cur[-1].end
            too_long = (w.end - cur[0].start) > max_dur
            punct = cur[-1].text[-1:] in ".,!?;" and len(cur) >= 3
            if gap > max_gap or len(cur) >= max_words or too_long or punct:
                flush()
        cur.append(w)
    flush()
    # don't leave a single word stranded on its own line
    merged: list[Line] = []
    for ln in lines:
        prev = merged[-1] if merged else None
        if prev and len(ln.words) == 1 and ln.start - prev.end <= max_gap \
                and len(prev.words) <= max_words + 1:
            prev.words += ln.words
            prev.text += " " + ln.text
            prev.end = ln.end
        else:
            merged.append(ln)
    return merged


def write_lyrics(path: str | Path, lf: LyricsFile, words_path: str | Path | None = None):
    path = Path(path)
    out = [HEADER, f"clip_start = {lf.clip_start:.2f}", f"clip_length = {lf.clip_length:g}", ""]
    for ln in lf.lines:
        out.append(f"[{fmt_time(ln.start)} --> {fmt_time(ln.end)}] {ln.text}")
    path.write_text("\n".join(out) + "\n", encoding="utf-8")
    if words_path:
        Path(words_path).write_text(
            json.dumps([asdict(ln) for ln in lf.lines], indent=1), encoding="utf-8")


def parse_lyrics(text: str) -> LyricsFile:
    lf = LyricsFile(lines=[])
    for num, raw in enumerate(text.splitlines(), 1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        m = _SETTING.match(line)
        if m:
            key, val = m.group(1).lower(), float(m.group(2))
            if key == "clip_start":
                lf.clip_start = val
            elif key == "clip_length":
                lf.clip_length = val
            continue
        m = _TIMED.match(line)
        if not m:
            raise ValueError(
                f"Lyrics line {num} has no timestamps: {raw!r}\n"
                "  Expected:  [00:12.30 --> 00:14.80] your lyric here")
        start, end = parse_time(m.group(1)), parse_time(m.group(2))
        if end <= start:
            raise ValueError(f"Lyrics line {num}: end time must be after start time")
        if m.group(3).strip():
            lf.lines.append(Line(start, end, m.group(3).strip()))
    lf.lines.sort(key=lambda ln: ln.start)
    return lf


def read_lyrics(path: str | Path) -> LyricsFile:
    return parse_lyrics(Path(path).read_text(encoding="utf-8"))


def _norm(s: str) -> str:
    return " ".join(re.sub(r"[^\w\s']", "", s.lower()).split())


def attach_word_timing(lf: LyricsFile, words_path: str | Path | None):
    """Give every line per-word timings.

    If a line is unchanged from the transcript (same words, overlapping time), the
    real Whisper word timings are reused. Edited lines get timings spread across the
    line in proportion to word length.
    """
    original: list[Line] = []
    if words_path and Path(words_path).exists():
        for d in json.loads(Path(words_path).read_text(encoding="utf-8")):
            original.append(Line(d["start"], d["end"], d["text"],
                                 [Word(**w) for w in d.get("words", [])]))
    for ln in lf.lines:
        match = next((o for o in original
                      if _norm(o.text) == _norm(ln.text) and o.words
                      and o.start < ln.end and ln.start < o.end), None)
        tokens = ln.text.split()
        if match and len(match.words) == len(tokens):
            ln.words = [Word(tok, min(max(w.start, ln.start), ln.end),
                             min(max(w.end, ln.start), ln.end))
                        for tok, w in zip(tokens, match.words)]
        else:
            ln.words = spread_words(tokens, ln.start, ln.end)
    return lf


def spread_words(tokens: list[str], start: float, end: float) -> list[Word]:
    if not tokens:
        return []
    weights = [len(t) + 2 for t in tokens]
    total = sum(weights)
    words, t = [], start
    for tok, wgt in zip(tokens, weights):
        d = (end - start) * wgt / total
        words.append(Word(tok, t, t + d))
        t += d
    return words
