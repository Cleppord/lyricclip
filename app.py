"""Browser UI:  python app.py   → opens http://127.0.0.1:7860

1. Upload your WAV (and optionally a vocals-only stem) → Get lyrics
2. Fix any wrong words in the lyrics box
3. Optionally upload clips/photos → Render
"""
from __future__ import annotations

import functools
import shutil
import tempfile
import traceback
import uuid
from pathlib import Path

import gradio as gr

from lyricclip.captions import STYLES
from lyricclip.lyrics import parse_lyrics
from lyricclip.pipeline import make_lyrics
from lyricclip.render import check_ffmpeg, render_video

WORK = Path(tempfile.gettempdir()) / "lyricclip_ui"
WORK.mkdir(exist_ok=True)
OUTPUT = Path("output")


def _path(f):
    return getattr(f, "name", f)  # gradio 3 gives file objects, 4+ gives paths


def show_errors(fn):
    """Show the real error in the browser instead of a bare 'Error' badge."""
    @functools.wraps(fn)
    def wrapper(*args, **kwargs):
        try:
            return fn(*args, **kwargs)
        except gr.Error:
            raise
        except FileNotFoundError as e:
            traceback.print_exc()
            if "ffmpeg" in str(e) or "ffprobe" in str(e) or getattr(e, "filename", None) in ("ffmpeg", "ffprobe"):
                raise gr.Error("ffmpeg isn't installed or isn't on PATH. Install it "
                               "(winget install --id Gyan.FFmpeg -e), then close and reopen the "
                               "terminal and run python app.py again.", duration=None)
            raise gr.Error(f"File not found: {e}", duration=None)
        except (Exception, SystemExit) as e:
            traceback.print_exc()
            raise gr.Error(f"{type(e).__name__}: {e}", duration=None)
    return wrapper


@show_errors
def get_lyrics(song, vocals, model, language, auto_start, start, length, blank,
               progress=gr.Progress()):
    if not song:
        raise gr.Error("Upload your song first.")
    check_ffmpeg()
    job = WORK / uuid.uuid4().hex[:8]
    job.mkdir()
    lyrics_path, words_path = job / "song.lyrics.txt", job / "song.words.json"
    progress(0.1, desc="Transcribing — this can take a minute or two")
    make_lyrics(_path(song), lyrics_path, words_path, vocals=_path(vocals) if vocals else None,
                model=model, language=language.strip() or None,
                start=None if auto_start else float(start), length=float(length), blank=blank,
                log=lambda m: progress(0.5, desc=m))
    return lyrics_path.read_text(encoding="utf-8"), str(words_path)


@show_errors
def render(song, lyrics_text, words_path, content, style, uppercase, beats_per_cut,
           mix_generated, count, progress=gr.Progress()):
    if not song:
        raise gr.Error("Upload your song first.")
    if not lyrics_text.strip():
        raise gr.Error("Get the lyrics first (or tick 'type lyrics myself').")
    check_ffmpeg()
    try:
        parse_lyrics(lyrics_text)
    except ValueError as e:
        raise gr.Error(str(e))

    content_dir = None
    if content:
        content_dir = WORK / ("content_" + uuid.uuid4().hex[:8])
        content_dir.mkdir()
        for f in content:
            shutil.copy(_path(f), content_dir / Path(_path(f)).name)

    stem = Path(_path(song)).stem
    outs = []
    for i in range(int(count)):
        progress((i + 0.1) / count, desc=f"Rendering video {i + 1} of {int(count)}")
        out = OUTPUT / f"{stem}_{uuid.uuid4().hex[:6]}.mp4"
        render_video(_path(song), parse_lyrics(lyrics_text), out, content_dir=content_dir,
                     style=style, beats_per_cut=int(beats_per_cut), uppercase=uppercase,
                     mix_generated=mix_generated, words_path=words_path or None)
        outs.append(str(out))
    return outs[0], outs


with gr.Blocks(title="lyricclip") as demo:
    gr.Markdown("# lyricclip\nYour song → 15-second vertical lyric video for TikTok.")
    words_state = gr.State("")
    with gr.Row():
        with gr.Column():
            gr.Markdown("### 1 · Song")
            song = gr.Audio(type="filepath", label="Your song (WAV)")
            vocals = gr.Audio(type="filepath", label="Optional: vocals-only stem (much better lyrics)")
            with gr.Accordion("Transcription settings", open=False):
                model = gr.Dropdown(["tiny", "base", "small", "medium", "large-v3"],
                                    value="small", label="Whisper model (bigger = more accurate, slower)")
                language = gr.Textbox(label="Language code (blank = auto)", placeholder="en")
                auto_start = gr.Checkbox(True, label="Auto-pick the hook (loudest part)")
                start = gr.Number(0, label="…or start at second")
                length = gr.Number(15, label="Clip length (s)")
                blank = gr.Checkbox(False, label="Skip Whisper — I'll type the lyrics myself")
            btn_lyrics = gr.Button("Get lyrics", variant="primary")
        with gr.Column():
            gr.Markdown("### 2 · Fix the lyrics\nRetype wrong words, adjust `[start --> end]` times, "
                        "or change `clip_start` to use a different part of the song.")
            lyrics = gr.Textbox(lines=18, label="Lyrics (editable)")
    gr.Markdown("### 3 · Render")
    with gr.Row():
        with gr.Column():
            content = gr.File(file_count="multiple", label="Background clips / photos (optional — "
                              "leave empty for generated visuals)")
            style = gr.Radio(list(STYLES), value="karaoke", label="Caption style")
            uppercase = gr.Checkbox(False, label="UPPERCASE lyrics")
            beats_per_cut = gr.Slider(1, 8, value=4, step=1, label="Cut every N beats")
            mix_generated = gr.Checkbox(False, label="Mix generated visuals in with my clips")
            count = gr.Slider(1, 5, value=1, step=1, label="How many variations")
            btn_render = gr.Button("Render video", variant="primary")
        with gr.Column():
            video = gr.Video(label="Preview")
            files = gr.File(label="Download", file_count="multiple")

    btn_lyrics.click(get_lyrics, [song, vocals, model, language, auto_start, start, length, blank],
                     [lyrics, words_state])
    btn_render.click(render, [song, lyrics, words_state, content, style, uppercase,
                              beats_per_cut, mix_generated, count], [video, files])

if __name__ == "__main__":
    check_ffmpeg()
    demo.queue().launch(inbrowser=True)
