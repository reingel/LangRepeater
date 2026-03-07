
# LangRepeater

## Overview
- A program that loads mp3 or mp4 files along with srt subtitle files, and repeatedly plays audio segments corresponding to the timestamps in the srt file, for the purpose of foreign language learning.
- A terminal-based program operated entirely by keyboard input.

## Development Language
- Python 3.11+
- Designed with future expansion in mind (iPhone, iPad, Android, web app).
- Core logic is separated into `langrepeater/core/` so it can later be wrapped as a FastAPI server and consumed by Flutter or React Native clients.

## Tech Stack

| Purpose | Library |
|---|---|
| Audio playback (mp3) | `pygame` (pygame.mixer.music with seek) |
| Audio playback (mp4) | `python-vlc` |
| SRT parsing | `srt` |
| Keyboard input | `pynput` |
| Terminal UI | `rich` |
| YAML persistence | `pyyaml` |
| Packaging | `pyproject.toml` + `setuptools` |

## Functional Requirements
- Running `LangRepeater` in the terminal launches the program and displays a brief usage guide.
- LangRepeater searches the current directory for:
    - mp3 and mp4 files
        - If found, displays a list and prompts the user to select one.
        - The selected file is used as the media file.
    - srt files
        - If found, displays a list and prompts the user to select one.
        - The selected file is used as the subtitle file.
    - If no files are found in the current directory, the user is prompted to enter a path, and the search is performed in that path.
- Once both files are selected, the first 3 subtitles are displayed, with the first subtitle shown in bold.
- When the user presses the play key (see Keyboard Mapping below), the audio segment corresponding to the current subtitle is played. (For mp4 files, only audio is played, not video.)
- Pressing the play key again replays the same segment.
- Pressing the next key advances to the next subtitle, plays it, and displays the previous, current, and next subtitles with the current one in bold.
- Pressing the previous key goes back to the previous subtitle, plays it, and displays 3 subtitles similarly.
- Learning statistics are recorded in `stat.yaml` under a section keyed by the media filename:
    - Progress (current subtitle index / total subtitles, as a percentage)
    - Play count per subtitle
    - Total play count
- Pressing the quit key exits the program.
- Before exiting, the current media file, subtitle file, and segment position are saved to `progress.yaml`.
- On the next launch, if `progress.yaml` exists, its contents are displayed and the user is asked whether to resume or open a new file.
- If a new file is selected and the user exits, the current session is added to `progress.yaml` without removing the previous record.
- On the next launch, if `progress.yaml` contains two or more sessions, the user is first asked which session to continue.

## Keyboard Mapping
- Play: Space, S
- Next segment: Right arrow, D
- Previous segment: Left arrow, A
- Quit: Q, ESC

## Project Structure

```
LangRepeater/
├── pyproject.toml
├── REQUIREMENTS.md
└── langrepeater/
    ├── __init__.py
    ├── main.py              # Entry point: LangRepeater command → main()
    ├── app.py               # AppController: CLI orchestrator
    ├── ui.py                # RichUI: terminal rendering
    ├── keyboard_handler.py  # KeyboardHandler: pynput-based async input
    └── core/                # Platform-independent core (portable to API server)
        ├── __init__.py
        ├── models.py        # Dataclasses: Subtitle, Session, SessionStats
        ├── file_finder.py   # mp3/mp4/srt file discovery (OS-agnostic)
        ├── srt_parser.py    # SRT parsing → list[Subtitle]
        ├── audio_player.py  # AudioPlayer (abstract), PygameAudioPlayer, VLCAudioPlayer
        ├── progress_store.py# progress.yaml read/write
        └── stats_store.py   # stat.yaml read/write
```

## Installation & Usage

```bash
pip install -e .
LangRepeater
```

## OS Compatibility Notes

| Item | Note |
|---|---|
| `file_finder.py` | Uses `.suffix.lower()` for case-insensitive search (macOS/Windows/Linux) |
| `pynput` (macOS) | Requires Accessibility permission in System Settings |
| `python-vlc` | Requires VLC media player installed on the system |

## Future Expansion Roadmap

- **Phase 1 (current)**: Python CLI MVP
- **Phase 2**: Expose `langrepeater/core/` as a FastAPI REST API server
- **Phase 3**: Flutter or React Native client → desktop / web / mobile UI via API
