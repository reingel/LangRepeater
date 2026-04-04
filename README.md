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

A model file is also required. Place it under `models/` in the project root:

```bash
mkdir -p models
# Download the small model (recommended)
curl -L -o models/ggml-small.bin \
  https://huggingface.co/ggerganov/whisper.cpp/resolve/main/ggml-small.bin
```

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

### Listen & Repeat mode (default)

Plays each segment. Use `Space` to play/pause, `S` to replay from the start, and `D`/`A` to navigate segments. Subtitles are shown with middle words masked; press `V` to reveal. Press `T` to enter transcribe mode for the current segment.

### Listening mode

Plays the entire file continuously from the current segment. Subtitles update automatically as playback progresses. Press `1` to enter, `2` to return to Listen & Repeat mode. Play counts are not recorded in Listening mode.

---

## Keyboard Shortcuts

### Mode

| Action | Key |
|---|---|
| Listening mode | `1` |
| Listen & Repeat mode | `2` |

### Playback

| Action | Key |
|---|---|
| Play / pause current segment | `Space` |
| Replay from start | `S` |
| Next segment | `D` / `→` / `↓` |
| Previous segment | `A` / `←` / `↑` |
| Skip forward 3 segments | `]` |
| Skip backward 3 segments | `[` |
| Go to segment by number | `G` |
| Show / hide subtitle | `V` |
| Quit | `Q` |
| Home screen | `ESC` |

### Transcribe

Press `T` to enter transcribe mode for the current segment.

| Action | Key |
|---|---|
| Enter transcribe mode | `T` |
| Restart playback while typing | `Tab` |
| Show / hide subtitle while typing | `Opt+V` |
| Cancel | `ESC` |

Type the sentence you heard and press `Enter`. Correct words are shown in green, incorrect words in red. A 👍 is displayed if the entire sentence is correct.

### Timestamp Adjustment

| Action | Key |
|---|---|
| Start time −0.1s | `Z` |
| Start time +0.1s | `X` |
| End time −0.1s | `,` |
| End time +0.1s | `.` |

### Editing

| Action | Key |
|---|---|
| Merge with next segment | `U` |
| Split current segment | `I` |

When splitting (`I`), candidate split points (punctuation or conjunctions) are highlighted inline. Enter the number to split at that point, or `C` to cancel. The split timestamp is calculated proportionally by word count.

### Statistics

| Action | Key |
|---|---|
| Segment stats (play count ranking) | `P` |
| Date stats (daily activity) | `0` |
| Next page | `]` |
| Previous page | `[` |
| Back to study | any other key |

`]` / `[` navigate stats pages while a stats screen is open, and skip 3 segments at a time during normal playback. Segment stats show the top segments by play count plus total learning time. Date stats show daily segment/repeat counts and net play time. Play counts are updated on merge/split. Play counts are recorded in Listen & Repeat mode only.
