# LangRepeater

A language-learning tool that repeatedly plays audio segments from MP3/MP4 files synced with SRT subtitles.

---

## Installation

```bash
pip install -e ".[dev]"
```

---

## Usage

### macOS GUI App

```bash
LangRepeaterMac
```

1. The API server starts automatically in the background on port 8000.
2. If a previous session exists, you will be asked whether to resume it. Enter the session number or cancel to open a new file.
3. Click **Open Files** in the top-right corner.
   - Select a media file (`.mp3` or `.mp4`).
   - Then select a subtitle file (`.srt`).
4. The current, previous, and next subtitles are displayed. Use the keyboard to navigate.

### Keyboard Shortcuts

| Action | Key |
|---|---|
| Play (repeat current segment) | `Space` / `S` |
| Next segment | `→` / `D` |
| Previous segment | `←` / `A` |
| Quit | `Q` / `Esc` |

Your position is saved automatically on quit and restored on the next launch.

---

### Terminal CLI

```bash
LangRepeater
```

### API Server only

```bash
LangRepeaterAPI          # http://localhost:8000
# Interactive docs: http://localhost:8000/docs
```

---

## Development / Tests

```bash
pytest
```
