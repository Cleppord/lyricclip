"""Shared steps used by both the CLI and the web UI."""
from __future__ import annotations

from pathlib import Path

from .audio import SR, estimate_beats, load_mono, loudest_window, snap_to_beat
from .lyrics import Line, LyricsFile, words_to_lines, write_lyrics


def pick_start(song: str | Path, length: float) -> float:
    """Start of the loudest `length` seconds (usually the hook), snapped to a beat."""
    y = load_mono(song)
    start = loudest_window(y, SR, length)
    _, beats = estimate_beats(y)
    return round(snap_to_beat(start, beats), 2)


def make_lyrics(song: str | Path, out: str | Path, words_out: str | Path,
                vocals: str | Path | None = None, model: str = "small",
                language: str | None = None, start: float | None = None,
                length: float = 15.0, blank: bool = False, vad: bool = False,
                log=print) -> LyricsFile:
    if start is None:
        start = pick_start(song, length)
        log(f"Auto-picked the loudest {length:g}s (likely the hook) at {start:.2f}s")
    if blank:
        lines = [Line(start + 0.5, start + 3.0, "type your first lyric here")]
    else:
        from .transcribe import transcribe_words
        lines = words_to_lines(
            transcribe_words(vocals or song, model, language, vad=vad, progress=log))
    lf = LyricsFile(lines, start, length)
    write_lyrics(out, lf, words_out)
    return lf
