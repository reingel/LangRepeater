# LangRepeater

A language-learning tool that repeatedly plays audio segments from MP3/MP4 files synced with SRT subtitles.

---

## Requirements

The following external tools must be installed before using LangRepeater:

### ffmpeg

Required for extracting audio from MP4 files.

```bash
brew install ffmpeg
```

### yt-dlp

Required for downloading audio from URLs.

```bash
brew install yt-dlp
# or
pip install yt-dlp
```

### whisper-cli

Required for auto-generating subtitle files from audio.

Install [whisper.cpp](https://github.com/ggerganov/whisper.cpp) and make `whisper-cli` available in your PATH.

A model file is also required. Place it under `models/` in the project root.

Available models (larger = more accurate, slower):

| Model | Size | Command |
|---|---|---|
| tiny | ~75 MB | `bash models/download-ggml-model.sh tiny` |
| base | ~142 MB | `bash models/download-ggml-model.sh base` |
| small | ~466 MB | `bash models/download-ggml-model.sh small` |
| medium | ~1.5 GB | `bash models/download-ggml-model.sh medium` |
| large-v3 | ~3.1 GB | `bash models/download-ggml-model.sh large-v3` |

The `download-ggml-model.sh` script is included in the whisper.cpp repository. Run it from the project root, or download manually:

```bash
mkdir -p models

# Option 1: use the whisper.cpp download script (recommended)
bash /path/to/whisper.cpp/models/download-ggml-model.sh small
cp /path/to/whisper.cpp/models/ggml-small.bin models/

# Option 2: download directly with curl
curl -L -o models/ggml-small.bin \
  https://huggingface.co/ggerganov/whisper.cpp/resolve/main/ggml-small.bin
```

`small` is recommended for a good balance of speed and accuracy. Update the model path in the transcription command if you use a different model.

---

## Installation

```bash
pip install -e ".[dev]"
```

---

## Usage

### Terminal CLI

```bash
LangRepeater
```

1. If a previous session exists, you will be asked whether to resume it. Enter the session number or cancel to open a new file.
2. Select a media file (`.mp3` or `.mp4`) and a subtitle file (`.srt`), or enter a URL to download.
3. The current, previous, and next subtitles are displayed. Subtitles are shown with middle words hidden — press `V` to reveal.

---

## Modes

### Review mode (key: `1`)

Samples ~10 previously studied segments weighted by play count and lets you review them in Listen & Repeat style. Press `R` to resample. Progress shows `xx/10`. Play counts are recorded.

### Listen & Repeat mode (default, key: `2`)

Plays each segment one at a time. Use `Space` to play/pause, `S` to replay from the start, and `D`/`A` to navigate. Subtitles are shown with middle words masked; press `V` to reveal. Press `T` to enter transcribe mode. Play counts are recorded.

### Listening mode (key: `3`)

Plays the entire file continuously from the current segment. Subtitles update automatically as playback progresses. Play counts are **not** recorded in Listening mode.

---

## Keyboard Shortcuts

### Mode Selection

| Key | Mode |
|---|---|
| `1` | Review mode |
| `2` | Listen & Repeat mode |
| `3` | Listening mode |

### Navigation

| Key | Action |
|---|---|
| `D` / `→` / `↓` | Next segment |
| `A` / `←` / `↑` | Previous segment |
| `]` | Skip forward 3 segments |
| `[` | Skip backward 3 segments |
| `G` | Go to segment by number |
| `Backspace` | Go back to previously played segment |

### Playback

| Key | Action |
|---|---|
| `Space` | Play / pause current segment |
| `S` | Replay from start |
| `V` | Show / hide subtitle |
| `Q` | Quit |
| `ESC` | Home screen |

### Transcribe (press `T` to enter)

| Key | Action |
|---|---|
| `Tab` | Restart playback while typing |
| `Opt+V` | Show / hide subtitle while typing |
| `Enter` | Submit answer |
| `ESC` | Cancel |

Type the sentence you heard and press `Enter`. Correct words are shown in green, wrong case/punctuation in yellow, incorrect words in red. A 👍 is displayed if the entire sentence matches.

### Timestamp Adjustment (Listen & Repeat / Review mode)

| Key | Action |
|---|---|
| `Z` | Start time −0.1s |
| `X` | Start time +0.1s |
| `,` | End time −0.1s |
| `.` | End time +0.1s |

### Segment Editing (Listen & Repeat mode only)

| Key | Action |
|---|---|
| `U` | Merge with next segment |
| `I` | Split current segment |

When splitting (`I`), candidate split points (punctuation or conjunctions) are highlighted inline. Enter the number to split at that point, or `C` to cancel.

### Statistics

| Key | Action |
|---|---|
| `P` | Segment stats (play count per segment) |
| `0` | Date stats (daily activity) |
| `R` | Resample review list (Review mode) |
| `]` | Next stats page |
| `[` | Previous stats page |
| any other key | Back to study |

Segment stats show segments in order with play counts and total learning time. Date stats show daily segment/repeat counts and net play time. `]` / `[` navigate stats pages while a stats screen is open, and skip 3 segments during normal playback.
