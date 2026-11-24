# lyricclip 🎵📱

Turn a song you made into a **15-second vertical lyric video** ready for TikTok.

1. **Upload your WAV** → Whisper transcribes the lyrics with word-level timing
2. **Fix any wrong words** in a plain text file (or in the browser UI)
3. **Render** → random clips/photos cut on the beat, your song underneath, lyrics burned in

Output: 1080×1920 · 30 fps · H.264 + AAC · exactly 15.0 s. Upload it straight to TikTok.

Everything runs locally. No API keys, no uploads.

---

## Setup

You need **Python 3.9+** and **ffmpeg**.

```bash
# ffmpeg
brew install ffmpeg            # macOS
sudo apt install ffmpeg        # Ubuntu/Debian
winget install ffmpeg          # Windows

# lyricclip
git clone https://github.com/<you>/lyricclip.git
cd lyricclip
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -e ".[ui]"
```

The first transcription downloads the Whisper model (~500 MB for `small`).

## Option A: browser UI

```bash
python app.py
```

Open http://127.0.0.1:7860, upload your song and click **Get lyrics**. Fix anything in the lyrics box, add clips if you have them, then click **Render video**.

## Option B: command line

```bash
# 1. transcribe → writes mysong.lyrics.txt (+ mysong.words.json with word timings)
lyricclip transcribe mysong.wav

# 2. open mysong.lyrics.txt and fix any wrong words

# 3. render → output/mysong.mp4
lyricclip render mysong.wav
```

### The lyrics file

```text
clip_start = 42.50
clip_length = 15

[00:42.80 --> 00:45.10] I been running all night
[00:45.30 --> 00:47.90] city lights in my eyes
```

- **Wrong word?** Retype it. Unchanged lines keep Whisper's exact word timing. Edited lines get timing spread across the line, which looks right in nearly every case.
- **Wrong timing?** Change the `[start --> end]` times. They are positions in the **full song**.
- **Missing or extra line?** Add it or delete it.
- **Wrong part of the song?** Change `clip_start`. By default it auto-picks the loudest 15 seconds, which is usually the hook.

## Getting better lyrics

Sung vocals over a beat are much harder to transcribe than speech. In order of impact:

1. **Give it your vocal stem.** You made the song, so export the vocals on their own:
   `lyricclip transcribe mysong.wav --vocals vocals.wav`
   The video still uses the full mix. The stem is only used for transcription.
2. **Use a bigger model:** `--model medium` or `--model large-v3`. These are slower but noticeably better.
3. **Set the language:** `--language en`.
4. If it's hopeless (heavy effects, mumbled ad-libs), run `--blank` and type the lyrics into the template. Then adjust the times.

## Background content

Put clips and photos in `content/`. Each render:

- picks random files and random moments inside them
- cuts on the beat (it detects the tempo; `--beats-per-cut 2` gives a faster edit)
- center-crops everything to vertical and adds a slow zoom to photos

With an empty `content/` folder you get built-in generated visuals (fractal zooms, cellular automata, gradients). Add `--mix-generated` to mix them in with your own footage.

Only use footage you have the rights to, such as your own clips or royalty-free libraries like Pexels or Pixabay.

## Options

| `render` flag | What it does |
|---|---|
| `--style karaoke` | Full line shown, words fill gold as they're sung (default) |
| `--style pop` | 1–3 big words at a time that punch in |
| `--style lines` | Plain line-by-line captions |
| `--count 5` | 5 variations with different random cuts, for A/B testing posts |
| `--seed 42` | Repeat the exact same random picks |
| `--start 63.5` | Override `clip_start` without editing the file |
| `--uppercase` | ALL CAPS lyrics |
| `--font "Montserrat Black"` | Any font installed on your system |
| `--content path/` | Use a different footage folder |
| `-o out.mp4` | Output path |

Captions sit a little below center so TikTok's caption, buttons and progress bar don't cover them.

## Project layout

```
lyricclip/
  transcribe.py   faster-whisper → word timestamps
  lyrics.py       editable lyrics file format + word-timing matching
  audio.py        decoding, hook finder, beat tracker (numpy only)
  background.py   random footage selection + beat-aligned cut plan
  captions.py     .ass subtitle styles (karaoke / pop / lines)
  render.py       ffmpeg composition
  cli.py          `lyricclip` command
app.py            Gradio browser UI
tests/            pytest (no Whisper needed)
```

## Tests

```bash
pip install pytest && pytest
```
