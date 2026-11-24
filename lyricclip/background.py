"""Pick random background footage and plan the cuts."""
from __future__ import annotations

import random
from dataclasses import dataclass
from pathlib import Path

from .audio import ffprobe_duration

VIDEO_EXT = {".mp4", ".mov", ".m4v", ".mkv", ".webm", ".avi"}
IMAGE_EXT = {".jpg", ".jpeg", ".png", ".webp", ".bmp"}

# Built-in generated visuals, used when you have no footage (or mixed in with --mix-generated)
GENERATORS = [
    "mandelbrot=s=540x960:rate=30:maxiter=200:start_x={mx}:start_y={my}:start_scale={ms},hue=h={hue}+t*35",
    "life=s=270x480:rate=30:ratio=0.12:mold=12:life_color=#ff2e88:death_color=#12002a:mold_color=#3a0ca3",
    "cellauto=s=270x480:rate=30:rule={rule}:scroll=1,negate,colorchannelmixer=rr=1:gg=0.25:bb=0.9",
    "gradients=s=540x960:rate=30:speed=0.03:nb_colors=4:seed={seed}:c0=#ff006e:c1=#3a86ff:c2=#8338ec:c3=#06d6a0",
]


MANDEL_SPOTS = [(-0.743643887, 0.131825904), (-0.7453, 0.1127), (-1.25066, 0.02012),
                (-0.10110, 0.95629), (-0.7746806, 0.1374168), (-1.7685, 0.00172)]


@dataclass
class Segment:
    kind: str          # "video" | "image" | "generated"
    source: str        # file path or lavfi graph
    start: float       # offset into the source (video only)
    duration: float
    loop: bool = False  # source shorter than the segment


def find_media(content_dir: str | Path | None) -> list[Path]:
    if not content_dir:
        return []
    root = Path(content_dir)
    if not root.exists():
        raise SystemExit(f"Content folder not found: {root}")
    return sorted(p for p in root.rglob("*")
                  if p.is_file() and p.suffix.lower() in VIDEO_EXT | IMAGE_EXT
                  and not p.name.startswith("."))


def cut_durations(length: float, beats, beats_per_cut: int, rng: random.Random,
                  min_cut: float = 0.9) -> list[float]:
    """Cut lengths that add up to `length`, landing on beats when we know them."""
    cuts: list[float] = []
    if beats is not None and len(beats) >= beats_per_cut * 2:
        points = [b for b in beats[::beats_per_cut] if min_cut <= b <= length - min_cut]
        t = 0.0
        for p in points:
            if p - t >= min_cut:
                cuts.append(p - t)
                t = p
        cuts.append(length - t)
    else:
        t = 0.0
        while length - t > 0:
            d = rng.uniform(1.6, 3.2)
            if length - t - d < min_cut:
                d = length - t
            cuts.append(d)
            t += d
    return cuts


def plan_segments(durations: list[float], media: list[Path], rng: random.Random,
                  mix_generated: bool = False) -> list[Segment]:
    sources: list[str | Path] = list(media)
    if not sources or mix_generated:
        sources += ["gen"] * max(1, len(media) // 3 if media else 1)
    dur_cache: dict[Path, float] = {}
    segs: list[Segment] = []
    last = None
    gen_cycle: list[str] = []
    for d in durations:
        choices = [s for s in sources if s != last] or sources
        src = rng.choice(choices)
        last = src
        if src == "gen":
            if not gen_cycle:  # go through every generator before repeating one
                gen_cycle = rng.sample(GENERATORS, len(GENERATORS))
                if segs and segs[-1].kind == "generated" and \
                        segs[-1].source.split("=")[0] == gen_cycle[-1].split("=")[0]:
                    gen_cycle.reverse()
            mx, my = rng.choice(MANDEL_SPOTS)
            graph = gen_cycle.pop().format(
                rule=rng.choice([30, 90, 110, 150, 182]), seed=rng.randint(0, 2**31 - 1),
                mx=mx, my=my, ms=round(rng.uniform(0.02, 0.6), 3), hue=rng.randint(0, 359))
            segs.append(Segment("generated", graph, 0.0, d))
        elif src.suffix.lower() in IMAGE_EXT:
            segs.append(Segment("image", str(src), 0.0, d))
        else:
            total = dur_cache.setdefault(src, ffprobe_duration(src))
            if total > d + 0.2:
                segs.append(Segment("video", str(src), rng.uniform(0, total - d - 0.1), d))
            else:
                segs.append(Segment("video", str(src), 0.0, d, loop=True))
    return segs
