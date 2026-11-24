"""Command line:  lyricclip transcribe song.wav   →  edit song.lyrics.txt  →  lyricclip render song.wav"""
from __future__ import annotations

import argparse
import random
from pathlib import Path

from .captions import STYLES


def _default_lyrics(song: Path) -> Path:
    return Path.cwd() / f"{song.stem}.lyrics.txt"


def cmd_transcribe(a):
    from .pipeline import make_lyrics
    from .render import check_ffmpeg, words_path_for

    check_ffmpeg()
    song = Path(a.song)
    out = Path(a.out) if a.out else _default_lyrics(song)
    lf = make_lyrics(song, out, words_path_for(out), vocals=a.vocals, model=a.model,
                     language=a.language, start=None if a.start == "auto" else float(a.start),
                     length=a.length, blank=a.blank, vad=a.vad)
    end = lf.clip_start + lf.clip_length
    in_clip = [ln for ln in lf.lines if ln.end > lf.clip_start and ln.start < end]
    print(f"\nWrote {out}  ({len(lf.lines)} lines, {len(in_clip)} inside the clip)")
    print("Open it, fix any wrong words, then run:")
    print(f"  lyricclip render {song} --lyrics {out}")


def cmd_render(a):
    from .lyrics import read_lyrics
    from .render import check_ffmpeg, render_video, words_path_for

    check_ffmpeg()
    song = Path(a.song)
    lyrics = Path(a.lyrics) if a.lyrics else _default_lyrics(song)
    if not lyrics.exists():
        raise SystemExit(f"No lyrics file at {lyrics}. Run `lyricclip transcribe {song}` first.")
    out = Path(a.out) if a.out else Path.cwd() / "output" / f"{song.stem}.mp4"
    base_seed = a.seed if a.seed is not None else random.randrange(1_000_000)
    for i in range(a.count):
        target = out if a.count == 1 else out.with_name(f"{out.stem}_{i + 1}{out.suffix}")
        seed = base_seed + i
        print(f"\n▶ Rendering {target.name} (seed {seed})")
        lf = read_lyrics(lyrics)
        if a.start is not None:
            lf.clip_start = a.start
        render_video(song, lf, target, content_dir=a.content, style=a.style, seed=seed,
                     beats_per_cut=a.beats_per_cut, font=a.font, uppercase=a.uppercase,
                     mix_generated=a.mix_generated, captions=not a.no_captions,
                     words_path=words_path_for(lyrics))


def main(argv=None):
    p = argparse.ArgumentParser(prog="lyricclip",
                                description="Turn a WAV into a 15s vertical lyric video for TikTok.")
    sub = p.add_subparsers(dest="cmd", required=True)

    t = sub.add_parser("transcribe", help="Get timed lyrics from your song into an editable file")
    t.add_argument("song", help="your song (.wav, also .mp3/.flac)")
    t.add_argument("--vocals", help="optional vocals-only stem — much more accurate lyrics")
    t.add_argument("--model", default="small",
                   help="Whisper size: tiny, base, small, medium, large-v3 (bigger = better, slower)")
    t.add_argument("--language", help="e.g. en — skips auto-detect")
    t.add_argument("--start", default="auto", help="clip start in seconds, or 'auto' (loudest part)")
    t.add_argument("--length", type=float, default=15.0, help="clip length in seconds")
    t.add_argument("--vad", action="store_true", help="skip non-vocal parts (can help or hurt)")
    t.add_argument("--blank", action="store_true", help="skip Whisper; write a template to type lyrics into")
    t.add_argument("-o", "--out", help="lyrics file to write (default: <song>.lyrics.txt)")
    t.set_defaults(func=cmd_transcribe)

    r = sub.add_parser("render", help="Make the video")
    r.add_argument("song")
    r.add_argument("--lyrics", help="lyrics file (default: <song>.lyrics.txt)")
    r.add_argument("--content", default="content", help="folder of clips/images to cut between")
    r.add_argument("--style", choices=STYLES, default="karaoke")
    r.add_argument("--count", type=int, default=1, help="render N variations with different cuts")
    r.add_argument("--seed", type=int, help="make the random picks repeatable")
    r.add_argument("--start", type=float, help="override clip_start from the lyrics file")
    r.add_argument("--beats-per-cut", type=int, default=4, help="cut every N beats (2 = faster edit)")
    r.add_argument("--font", default="Arial")
    r.add_argument("--uppercase", action="store_true")
    r.add_argument("--mix-generated", action="store_true",
                   help="mix built-in abstract visuals in with your footage")
    r.add_argument("--no-captions", action="store_true")
    r.add_argument("-o", "--out", help="output .mp4 (default: output/<song>.mp4)")
    r.set_defaults(func=cmd_render)

    a = p.parse_args(argv)
    if getattr(a, "content", None) == "content" and not Path("content").exists():
        a.content = None  # no footage folder → generated visuals
    a.func(a)


if __name__ == "__main__":
    main()
