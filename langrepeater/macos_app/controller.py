"""App controller: subtitle navigation and session/stats management.

Deliberately free of any GUI dependencies so it can be unit-tested
without a display.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from langrepeater.macos_app.api_client import LangRepeaterClient


@dataclass
class AppState:
    media_path: str = ""
    srt_path: str = ""
    subtitles: list[dict] = field(default_factory=list)
    current_index: int = 0  # 0-based index into subtitles


class AppController:
    def __init__(self, client: LangRepeaterClient) -> None:
        self.client = client
        self.state = AppState()

    # ------------------------------------------------------------------
    # Session setup
    # ------------------------------------------------------------------

    def load_files(self, media_path: str, srt_path: str) -> None:
        subtitles = self.client.get_subtitles(srt_path)
        self.state.media_path = media_path
        self.state.srt_path = srt_path
        self.state.subtitles = subtitles
        self.state.current_index = 0

    def resume_session(self, session: dict) -> None:
        subtitles = self.client.get_subtitles(session["srt_path"])
        self.state.media_path = session["media_path"]
        self.state.srt_path = session["srt_path"]
        self.state.subtitles = subtitles
        self.state.current_index = session.get("current_index", 0)

    # ------------------------------------------------------------------
    # Playback
    # ------------------------------------------------------------------

    def play_current(self) -> None:
        if not self.state.subtitles:
            return
        sub = self.current_subtitle()
        self.client.play(self.state.media_path, sub["start"], sub["end"])
        self.client.increment_play(self.state.media_path, sub["index"])

    def stop(self) -> None:
        self.client.stop()

    # ------------------------------------------------------------------
    # Navigation
    # ------------------------------------------------------------------

    def go_next(self) -> bool:
        """Advance to the next subtitle. Returns True if position changed."""
        if self.state.current_index < len(self.state.subtitles) - 1:
            self.state.current_index += 1
            return True
        return False

    def go_prev(self) -> bool:
        """Go back to the previous subtitle. Returns True if position changed."""
        if self.state.current_index > 0:
            self.state.current_index -= 1
            return True
        return False

    # ------------------------------------------------------------------
    # Display helpers
    # ------------------------------------------------------------------

    def current_subtitle(self) -> dict | None:
        if not self.state.subtitles:
            return None
        return self.state.subtitles[self.state.current_index]

    def display_window(self) -> tuple[dict | None, dict | None, dict | None]:
        """Return (prev, current, next) subtitle dicts for display."""
        subs = self.state.subtitles
        idx = self.state.current_index
        prev = subs[idx - 1] if idx > 0 else None
        curr = subs[idx] if subs else None
        nxt = subs[idx + 1] if idx < len(subs) - 1 else None
        return prev, curr, nxt

    def progress_text(self) -> str:
        total = len(self.state.subtitles)
        if total == 0:
            return ""
        pct = int((self.state.current_index + 1) / total * 100)
        return f"{self.state.current_index + 1}/{total}  ({pct}%)"

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    def save_progress(self) -> None:
        if self.state.media_path:
            self.client.upsert_session(
                self.state.media_path,
                self.state.srt_path,
                self.state.current_index,
            )
