"""Compose background cuts + song + burned-in lyrics into a 1080x1920 MP4."""
from __future__ import annotations

import random
import shutil
import subprocess
import tempfile
from pathlib import Path

from .audio import SR, estimate_beats, ffprobe_duration, load_mono
from .background import Segment, cut_durations, find_media, plan_segments
from .captions import H, W, build_ass
from .lyrics import LyricsFile, attach_word_timing, read_lyrics

FPS = 30


def words_path_for(lyrics_path: str | Path) -> Path:
    p = Path(lyrics_path)
    stem = p.name[:-len(".lyrics.txt")] if p.name.endswith(".lyrics.txt") else p.stem
    return p.with_name(stem + ".words.json")


def _segment_inputs(seg: Segment) -> tuple[list[str], str]:
    """ffmpeg input args and the per-input filter chain for one segment."""
    d = f"{seg.duration:.3f}"
    fit = f"scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H}"
    tail = f"fps={FPS},setsar=1,format=yuv420p,trim=duration={d},setpts=PTS-STARTPTS"
    if seg.kind == "video":
        args = (["-stream_loop", "-1"] if seg.loop else []) + \
               ["-ss", f"{seg.start:.3f}", "-t", d, "-i", str(Path(seg.source).resolve())]
        return args, f"{fit},{tail}"
    if seg.kind == "image":
        args = ["-loop", "1", "-framerate", str(FPS), "-t", d, "-i", str(Path(seg.source).resolve())]
        zoom = (f"scale=1188:2112:force_original_aspect_ratio=increase,crop=1188:2112,"
                f"zoompan=z='min(1+0.0012*on,1.12)':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)'"
                f":d=1:s={W}x{H}:fps={FPS}")
        return args, f"{zoom},{tail}"
    pixel = "life=" in seg.source or "cellauto=" in seg.source
    flags = ":flags=neighbor" if pixel else ""
    args = ["-f", "lavfi", "-t", d, "-i", seg.source]
    return args, f"scale={W}:{H}:force_original_aspect_ratio=increase{flags},crop={W}:{H},{tail}"


def render_video(song: str | Path, lyrics: LyricsFile | str | Path, out: str | Path,
                 content_dir: str | Path | None = None, style: str = "karaoke",
                 seed: int | None = None, beats_per_cut: int = 4, font: str = "Arial",
                 uppercase: bool = False, mix_generated: bool = False,
                 words_path: str | Path | None = None, captions: bool = True,
                 log=print) -> Path:
    song = Path(song).resolve()
    out = Path(out).resolve()
    if isinstance(lyrics, (str, Path)):
        words_path = words_path or words_path_for(lyrics)
        lf = read_lyrics(lyrics)
    else:
        lf = lyrics
    attach_word_timing(lf, words_path)

    total = ffprobe_duration(song)
    if total <= 0:
        raise SystemExit(f"Could not read audio: {song}")
    lf.clip_length = min(lf.clip_length, total)
    lf.clip_start = min(max(0.0, lf.clip_start), max(0.0, total - lf.clip_length))
    length = lf.clip_length

    rng = random.Random(seed)
    y = load_mono(song)
    clip = y[int(lf.clip_start * SR): int((lf.clip_start + length) * SR)]
    bpm, beats = estimate_beats(clip)
    if bpm:
        log(f"Tempo ≈ {bpm:.0f} BPM — cutting every {beats_per_cut} beats")
    durations = cut_durations(length, beats if bpm else None, beats_per_cut, rng)
    segs = plan_segments(durations, find_media(content_dir), rng, mix_generated)
    log(f"{len(segs)} cuts: " + ", ".join(
        f"{Path(s.source).name if s.kind != 'generated' else s.source.split('=')[0]}"
        f"({s.duration:.1f}s)" for s in segs))

    with tempfile.TemporaryDirectory(prefix="lyricclip_") as tmp:
        tmp = Path(tmp)
        (tmp / "captions.ass").write_text(
            build_ass(lf, style=style, font=font, uppercase=uppercase), encoding="utf-8")

        args, chains = [], []
        for i, seg in enumerate(segs):
            a, chain = _segment_inputs(seg)
            args += a
            chains.append(f"[{i}:v]{chain}[v{i}]")
        ai = len(segs)
        args += ["-ss", f"{lf.clip_start:.3f}", "-t", f"{length:.3f}", "-i", str(song)]

        concat = "".join(f"[v{i}]" for i in range(len(segs))) + \
                 f"concat=n={len(segs)}:v=1:a=0,eq=brightness=-0.04:saturation=1.08,vignette=PI/5"
        concat += ",ass=captions.ass[vout]" if captions else "[vout]"
        fade = max(0.0, length - 0.6)
        audio = f"[{ai}:a]afade=t=in:d=0.04,afade=t=out:st={fade:.3f}:d=0.6[aout]"
        graph = ";".join(chains + [concat, audio])

        out.parent.mkdir(parents=True, exist_ok=True)
        cmd = ["ffmpeg", "-y", "-v", "error", "-stats", *args,
               "-filter_complex", graph, "-map", "[vout]", "-map", "[aout]",
               "-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-pix_fmt", "yuv420p",
               "-r", str(FPS), "-c:a", "aac", "-b:a", "192k", "-ar", "44100",
               "-t", f"{length:.3f}", "-movflags", "+faststart", str(out)]
        proc = subprocess.run(cmd, cwd=tmp)  # cwd so the .ass path needs no escaping
        if proc.returncode != 0:
            raise SystemExit("ffmpeg failed — see the error above.")
    log(f"Saved {out}")
    return out


def _add_winget_links_to_path():
    """winget installs ffmpeg here, but already-open terminals don't see it yet."""
    import os
    links = Path(os.environ.get("LOCALAPPDATA", "")) / "Microsoft" / "WinGet" / "Links"
    if os.name == "nt" and links.is_dir() and str(links) not in os.environ.get("PATH", ""):
        os.environ["PATH"] = str(links) + os.pathsep + os.environ.get("PATH", "")


_add_winget_links_to_path()


def check_ffmpeg():
    if not shutil.which("ffmpeg") or not shutil.which("ffprobe"):
        raise SystemExit("ffmpeg (with ffprobe) must be installed and on your PATH. "
                         "See README → Setup.")
