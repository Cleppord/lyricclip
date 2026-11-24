"""Lyrics transcription with faster-whisper (runs locally, no API key)."""
from __future__ import annotations

from pathlib import Path

from .lyrics import Word


def transcribe_words(audio_path: str | Path, model_size: str = "small",
                     language: str | None = None, device: str = "auto",
                     vad: bool = False, progress=print) -> list[Word]:
    try:
        from faster_whisper import WhisperModel
    except ImportError as e:  # pragma: no cover
        raise SystemExit(
            "Transcription needs faster-whisper:  pip install faster-whisper") from e

    progress(f"Loading Whisper model '{model_size}' (first run downloads it)…")
    model = WhisperModel(model_size, device=device, compute_type="default")
    progress("Transcribing… (sung vocals are harder than speech — a vocal stem helps a lot)")
    segments, info = model.transcribe(
        str(audio_path),
        language=language or None,
        word_timestamps=True,
        beam_size=5,
        condition_on_previous_text=False,  # stops repeated-chorus hallucination loops
        vad_filter=vad,
    )
    words: list[Word] = []
    for seg in segments:
        for w in seg.words or []:
            text = w.word.strip()
            if text:
                words.append(Word(text, float(w.start), float(w.end)))
    progress(f"Got {len(words)} words (language: {info.language}).")
    return words
