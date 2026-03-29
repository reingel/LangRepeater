# LangRepeater

A language-learning tool that repeatedly plays audio segments from MP3/MP4 files synced with SRT subtitles.

---

## Requirements

The following external tools must be installed before using LangRepeater:

### ffmpeg

Required by Whisper to process audio files.

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

### Whisper

Required for auto-generating SRT subtitle files.

```bash
pip install openai-whisper
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

Plays each segment in a loop. Use `Space` to play/pause, `S` to replay from the start, and `D`/`A` to navigate segments.

### Listening mode

Plays the entire file continuously from the current segment. Subtitles update automatically as playback progresses. Press `1` to enter, `2` to return to Listen & Repeat mode.

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
| Show / hide subtitle | `V` |
| Quit | `Q` |
| Home screen | `ESC` |

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

Segment stats show the top segments by play count plus total learning time. Date stats show daily segment/repeat counts and net play time. Play counts are updated on merge/split.
