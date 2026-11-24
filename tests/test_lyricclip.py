"""Run with:  pytest   (needs ffmpeg; does not need Whisper)"""
import subprocess
import wave
from pathlib import Path

import numpy as np

from lyricclip.captions import build_ass
from lyricclip.lyrics import (LyricsFile, Word, attach_word_timing, parse_lyrics,
                              words_to_lines, write_lyrics)
from lyricclip.render import render_video


def _words(start=1.0):
    out, t = [], start
    for w in "hello world this is my song, sing it with me now".split():
        out.append(Word(w, t, t + 0.35))
        t += 0.45
    return out


def test_roundtrip_and_edit(tmp_path):
    lf = LyricsFile(words_to_lines(_words()), clip_start=0.5, clip_length=15)
    p, wp = tmp_path / "s.lyrics.txt", tmp_path / "s.words.json"
    write_lyrics(p, lf, wp)
    text = p.read_text().replace("hello world", "hey there world")  # user fixes a word
    back = parse_lyrics(text)
    assert back.clip_start == 0.5 and back.lines[0].text.startswith("hey there world")
    attach_word_timing(back, wp)
    assert len(back.lines[0].words) == len(back.lines[0].text.split())
    # unchanged line keeps Whisper's real timings
    assert back.lines[-1].words[0].start == lf.lines[-1].words[0].start


def test_bad_line_is_reported():
    try:
        parse_lyrics("clip_start = 0\njust some words")
    except ValueError as e:
        assert "line 2" in str(e)
    else:
        raise AssertionError("expected ValueError")


def test_ass_styles():
    lf = LyricsFile(words_to_lines(_words()), 0, 15)
    attach_word_timing(lf, None)
    for style in ("karaoke", "pop", "lines"):
        ass = build_ass(lf, style=style)
        assert ass.count("Dialogue:") >= 2


def test_render_smoke(tmp_path):
    sr = 22050
    t = np.arange(sr * 6) / sr
    y = (0.3 * np.sin(2 * np.pi * 220 * t) * 32767).astype(np.int16)
    song = tmp_path / "song.wav"
    with wave.open(str(song), "wb") as w:
        w.setnchannels(1), w.setsampwidth(2), w.setframerate(sr), w.writeframes(y.tobytes())
    lf = LyricsFile(words_to_lines(_words(0.5)), 0, 15)
    out = render_video(song, lf, tmp_path / "out.mp4", seed=1, log=lambda *_: None)
    probe = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v",
                            "-show_entries", "stream=width,height", "-of", "csv=p=0", str(out)],
                           capture_output=True, text=True).stdout.strip()
    assert probe == "1080,1920"
    assert Path(out).stat().st_size > 10_000
