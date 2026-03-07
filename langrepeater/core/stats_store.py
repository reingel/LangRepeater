from pathlib import Path

import yaml

from .models import SessionStats

DEFAULT_PATH = "stat.yaml"


class StatsStore:
    def __init__(self, path: str = DEFAULT_PATH):
        self.path = Path(path)

    def _load_raw(self) -> dict:
        if not self.path.exists():
            return {}
        try:
            data = yaml.safe_load(self.path.read_text(encoding="utf-8"))
            return data if isinstance(data, dict) else {}
        except Exception:
            return {}

    def _save_raw(self, data: dict) -> None:
        self.path.write_text(yaml.dump(data, allow_unicode=True), encoding="utf-8")

    def load(self, media_path: str) -> SessionStats:
        raw = self._load_raw()
        entry = raw.get(media_path, {})
        return SessionStats(
            media_path=media_path,
            total_play_count=entry.get("total_play_count", 0),
            subtitle_play_counts={
                int(k): v for k, v in entry.get("subtitle_play_counts", {}).items()
            },
        )

    def save(self, stats: SessionStats) -> None:
        raw = self._load_raw()
        raw[stats.media_path] = {
            "total_play_count": stats.total_play_count,
            "subtitle_play_counts": dict(stats.subtitle_play_counts),
        }
        self._save_raw(raw)

    def increment_play(self, media_path: str, subtitle_index: int) -> None:
        stats = self.load(media_path)
        stats.total_play_count += 1
        stats.subtitle_play_counts[subtitle_index] = (
            stats.subtitle_play_counts.get(subtitle_index, 0) + 1
        )
        self.save(stats)
