from datetime import date
from pathlib import Path

import yaml

from .models import SessionStats

SEGMENT_PATH = "stat-segment.yaml"
DATE_PATH = "stat-date.yaml"


class StatsStore:
    def __init__(self, segment_path: str = SEGMENT_PATH, date_path: str = DATE_PATH):
        self.path = Path(segment_path)
        self._date_path = Path(date_path)

    # ------------------------------------------------------------------
    # Segment stats (stat-segment.yaml)
    # ------------------------------------------------------------------

    def _load_raw(self) -> dict:
        if not self.path.exists():
            return {}
        try:
            data = yaml.safe_load(self.path.read_text(encoding="utf-8"))
            return data if isinstance(data, dict) else {}
        except Exception:
            return {}

    def _save_raw(self, data: dict) -> None:
        self.path.write_text(yaml.dump(data, allow_unicode=True, width=float("inf")), encoding="utf-8")

    def load(self, media_path: str) -> SessionStats:
        raw = self._load_raw()
        entry = raw.get(media_path, {})
        return SessionStats(
            media_path=media_path,
            total_play_count=entry.get("total_play_count", 0),
            subtitle_play_counts={
                int(k): v for k, v in entry.get("subtitle_play_counts", {}).items()
            },
            progress_pct=entry.get("progress_pct", 0.0),
        )

    def save(self, stats: SessionStats) -> None:
        raw = self._load_raw()
        raw[stats.media_path] = {
            "total_play_count": stats.total_play_count,
            "subtitle_play_counts": dict(stats.subtitle_play_counts),
            "progress_pct": stats.progress_pct,
        }
        self._save_raw(raw)

    def delete(self, media_path: str) -> None:
        raw = self._load_raw()
        if media_path in raw:
            del raw[media_path]
            self._save_raw(raw)
        self._delete_date_entry(media_path)

    def update_progress(self, media_path: str, current_index: int, total: int) -> None:
        stats = self.load(media_path)
        stats.progress_pct = (current_index + 1) / total * 100 if total > 0 else 0.0
        self.save(stats)

    def increment_play(self, media_path: str, subtitle_index: int) -> None:
        # Update segment stats
        stats = self.load(media_path)
        stats.total_play_count += 1
        stats.subtitle_play_counts[subtitle_index] = (
            stats.subtitle_play_counts.get(subtitle_index, 0) + 1
        )
        self.save(stats)
        # Update date stats
        self._increment_date_play(media_path, subtitle_index)

    def on_merge(self, media_path: str, cur_index: int, nxt_index: int, new_total: int) -> None:
        """Update stats after merging two adjacent subtitles (1-based indices)."""
        stats = self.load(media_path)
        counts = stats.subtitle_play_counts
        merged = counts.get(cur_index, 0) + counts.get(nxt_index, 0)
        new_counts: dict[int, int] = {}
        for idx, count in counts.items():
            if idx < cur_index:
                new_counts[idx] = count
            elif idx == cur_index:
                if merged:
                    new_counts[idx] = merged
            elif idx == nxt_index:
                pass  # absorbed into cur
            else:
                new_counts[idx - 1] = count
        new_counts = {k: v for k, v in new_counts.items() if v > 0 and k <= new_total}
        stats.subtitle_play_counts = new_counts
        stats.total_play_count = sum(new_counts.values())
        self.save(stats)

    def on_split(self, media_path: str, sub_index: int, new_total: int) -> None:
        """Update stats after splitting a subtitle (1-based index)."""
        stats = self.load(media_path)
        counts = stats.subtitle_play_counts
        original = counts.get(sub_index, 0)
        front = (original + 1) // 2
        back = original // 2
        new_counts: dict[int, int] = {}
        for idx, count in counts.items():
            if idx < sub_index:
                new_counts[idx] = count
            elif idx == sub_index:
                if front:
                    new_counts[idx] = front
            else:
                new_counts[idx + 1] = count
        if back:
            new_counts[sub_index + 1] = back
        new_counts = {k: v for k, v in new_counts.items() if v > 0 and k <= new_total}
        stats.subtitle_play_counts = new_counts
        stats.total_play_count = sum(new_counts.values())
        self.save(stats)

    # ------------------------------------------------------------------
    # Date stats (stat-date.yaml)
    # ------------------------------------------------------------------

    def _load_date_raw(self) -> dict:
        if not self._date_path.exists():
            return {}
        try:
            data = yaml.safe_load(self._date_path.read_text(encoding="utf-8"))
            return data if isinstance(data, dict) else {}
        except Exception:
            return {}

    def _save_date_raw(self, data: dict) -> None:
        self._date_path.write_text(yaml.dump(data, allow_unicode=True, width=float("inf")), encoding="utf-8")

    def _increment_date_play(self, media_path: str, subtitle_index: int) -> None:
        today = date.today().isoformat()
        raw = self._load_date_raw()
        media_entry = raw.setdefault(media_path, {})
        day_entry = media_entry.setdefault(today, {"total_play_count": 0, "subtitle_play_counts": {}})
        day_entry["total_play_count"] = day_entry.get("total_play_count", 0) + 1
        sc = day_entry.setdefault("subtitle_play_counts", {})
        sc[subtitle_index] = sc.get(subtitle_index, 0) + 1
        self._save_date_raw(raw)

    def _delete_date_entry(self, media_path: str) -> None:
        raw = self._load_date_raw()
        if media_path in raw:
            del raw[media_path]
            self._save_date_raw(raw)

    def load_date_stats(self, media_path: str) -> list[tuple[str, dict[int, int]]]:
        """Return list of (date_str, subtitle_play_counts) sorted newest first."""
        raw = self._load_date_raw()
        media_entry = raw.get(media_path, {})
        result = []
        for date_str, day_entry in media_entry.items():
            sc = {int(k): v for k, v in day_entry.get("subtitle_play_counts", {}).items()}
            result.append((date_str, sc))
        return sorted(result, key=lambda x: x[0], reverse=True)
