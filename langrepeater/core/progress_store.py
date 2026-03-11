from pathlib import Path

import yaml

from .models import Session

DEFAULT_PATH = "progress.yaml"


class ProgressStore:
    def __init__(self, path: str = DEFAULT_PATH):
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
                }
                for s in sessions
            ]
        }
        self.path.write_text(yaml.dump(data, allow_unicode=True, width=float("inf")), encoding="utf-8")

    def delete(self, index: int) -> None:
        sessions = self.load()
        if 0 <= index < len(sessions):
            sessions.pop(index)
            self.save(sessions)

    def upsert(self, session: Session) -> None:
        sessions = self.load()
        for i, s in enumerate(sessions):
            if s.media_path == session.media_path:
                sessions[i] = session
                self.save(sessions)
                return
        sessions.append(session)
        self.save(sessions)
