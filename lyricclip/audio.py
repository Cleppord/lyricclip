"""Audio helpers: decoding, finding the hook, and beat tracking (numpy only)."""
from __future__ import annotations

import json
import subprocess
from pathlib import Path

import numpy as np

SR = 22050


def ffprobe_duration(path: str | Path) -> float:
    """Duration of any media file in seconds (0.0 if unknown, e.g. still images)."""
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "json", str(path)],
        capture_output=True, text=True,
    )
    try:
        return float(json.loads(out.stdout)["format"]["duration"])
    except (KeyError, ValueError, json.JSONDecodeError):
        return 0.0


def load_mono(path: str | Path, sr: int = SR) -> np.ndarray:
    """Decode any audio file to mono float32 with ffmpeg."""
    proc = subprocess.run(
        ["ffmpeg", "-v", "error", "-i", str(path), "-ac", "1", "-ar", str(sr),
         "-f", "f32le", "-"],
        capture_output=True, check=True,
    )
    return np.frombuffer(proc.stdout, dtype=np.float32).copy()


def onset_envelope(y: np.ndarray, sr: int = SR, hop: int = 512, n_fft: int = 2048):
    """Spectral-flux onset strength. Returns (envelope, frames_per_second)."""
    fps = sr / hop
    if len(y) < n_fft * 2:
        return np.zeros(1, dtype=np.float32), fps
    window = np.hanning(n_fft).astype(np.float32)
    frames = np.lib.stride_tricks.sliding_window_view(y, n_fft)[::hop]
    mags = []
    for i in range(0, len(frames), 1024):  # chunk to keep memory low
        chunk = frames[i:i + 1024] * window
        mags.append(np.log1p(10.0 * np.abs(np.fft.rfft(chunk, axis=1))).astype(np.float32))
    logS = np.concatenate(mags)
    flux = np.maximum(0.0, np.diff(logS, axis=0)).sum(axis=1)
    flux = np.concatenate([[0.0], flux])
    # remove slow trend so autocorrelation sees the pulses
    k = int(fps)  # ~1 s
    trend = np.convolve(flux, np.ones(k) / k, mode="same")
    env = np.maximum(0.0, flux - trend)
    if env.max() > 0:
        env = env / env.max()
    return env.astype(np.float32), fps


def estimate_beats(y: np.ndarray, sr: int = SR, bpm_range=(70, 180)):
    """Rough global-tempo beat tracker. Returns (bpm, beat_times_seconds) or (None, [])."""
    env, fps = onset_envelope(y, sr)
    if len(env) < fps * 4 or env.max() == 0:
        return None, np.array([])
    n = len(env)
    spec = np.fft.rfft(env - env.mean(), n=2 * n)
    ac = np.fft.irfft(spec * np.conj(spec))[:n]
    lo = max(1, int(fps * 60 / bpm_range[1]))
    hi = min(n - 2, int(fps * 60 / bpm_range[0]))
    if hi <= lo:
        return None, np.array([])
    lags = np.arange(lo, hi + 1)
    bpms = 60 * fps / lags
    prior = np.exp(-0.5 * (np.log2(bpms / 120.0) / 0.9) ** 2)  # mild preference near 120
    score = ac[lags] * prior
    best = int(lags[np.argmax(score)])
    # parabolic refinement of the peak
    a, b, c = ac[best - 1], ac[best], ac[best + 1]
    denom = a - 2 * b + c
    shift = 0.5 * (a - c) / denom if denom != 0 else 0.0
    period = (best + float(np.clip(shift, -0.5, 0.5))) / fps
    # phase: offset that lands the most onset energy on the grid
    period_f = period * fps
    best_off, best_val = 0.0, -1.0
    for off in np.arange(0, period_f, 0.5):
        idx = np.round(np.arange(off, n, period_f)).astype(int)
        idx = idx[idx < n]
        val = env[idx].sum()
        if val > best_val:
            best_off, best_val = off, val
    beats = np.arange(best_off, n, period_f) / fps
    return 60.0 / period, beats


def loudest_window(y: np.ndarray, sr: int, length: float) -> float:
    """Start time (s) of the highest-energy `length`-second window — usually the hook/chorus."""
    total = len(y) / sr
    if total <= length:
        return 0.0
    step = sr // 10  # 0.1 s
    n = len(y) // step
    rms = np.sqrt(np.mean(y[: n * step].reshape(n, step) ** 2, axis=1))
    win = int(length * 10)
    csum = np.concatenate([[0.0], np.cumsum(rms)])
    energy = csum[win:] - csum[:-win]
    return float(np.argmax(energy)) / 10.0


def snap_to_beat(t: float, beats: np.ndarray, max_shift: float = 0.6) -> float:
    if len(beats) == 0:
        return t
    nearest = float(beats[np.argmin(np.abs(beats - t))])
    return nearest if abs(nearest - t) <= max_shift else t
