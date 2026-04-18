from pathlib import Path

import yaml

from .models import Session

_APP_DIR = Path.home() / ".langrepeater"
DEFAULT_PATH = _APP_DIR / "progress.yaml"


class ProgressStore:
    def __init__(self, path: Path = DEFAULT_PATH):
        self.path = Path(path)

    def load(self) -> list[Session]:
        if not self.path.exists():
            return []
        try:
            data = yaml.safe_load(self.path.read_text(encoding="utf-8"))
            sessions = data.get("sessions", []) if data else []
            return [
                Session(
                    media_path=s["media_path"],
                    srt_path=s["srt_path"],
                    current_index=s.get("current_index", 0),
                    total_segments=s.get("total_segments", 0),
                )
                for s in sessions
            ]
        except Exception:
            return []

    def save(self, sessions: list[Session]) -> None:
        data = {
            "sessions": [
                {
                    "media_path": s.media_path,
                    "srt_path": s.srt_path,
                    "current_index": s.current_index,
                    "total_segments": s.total_segments,
                }
                for s in sessions
            ]
        }
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(yaml.dump(data, allow_unicode=True, width=float("inf")), encoding="utf-8")

    def delete(self, index: int) -> None:
        sessions = self.load()
        if 0 <= index < len(sessions):
            sessions.pop(index)
            self.save(sessions)

    def upsert(self, session: Session) -> None:
        sessions = self.load()
        sessions = [s for s in sessions if s.media_path != session.media_path]
        sessions.insert(0, session)  # most recently used at front
        self.save(sessions)
