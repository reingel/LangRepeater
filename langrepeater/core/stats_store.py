from datetime import date
from pathlib import Path

import yaml

from .models import SessionStats

_APP_DIR = Path.home() / ".langrepeater"
SEGMENT_PATH = _APP_DIR / "stat-segment.yaml"
DATE_PATH = _APP_DIR / "stat-date.yaml"


class StatsStore:
    def __init__(self, segment_path: Path = SEGMENT_PATH, date_path: Path = DATE_PATH):
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
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(yaml.dump(data, allow_unicode=True, width=float("inf")), encoding="utf-8")

    def load(self, media_path: str) -> SessionStats:
        raw = self._load_raw()
        entry = raw.get(media_path, {})
        return SessionStats(
            media_path=media_path,
            total_play_count=entry.get("total_play_count", 0),
            subtitle_play_counts={
                str(k): v for k, v in entry.get("subtitle_play_counts", {}).items()
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

    def increment_play(self, media_path: str, subtitle_index: str) -> None:
        stats = self.load(media_path)
        stats.total_play_count += 1
        stats.subtitle_play_counts[subtitle_index] = (
            stats.subtitle_play_counts.get(subtitle_index, 0) + 1
        )
        self.save(stats)
        self._increment_date_play(media_path, subtitle_index)

    def on_merge(self, media_path: str, cur_idx: str, nxt_idx: str, result_idx: str) -> None:
        """Update stats after merging two adjacent subtitles."""
        stats = self.load(media_path)
        counts = stats.subtitle_play_counts
        merged = counts.pop(cur_idx, 0) + counts.pop(nxt_idx, 0)
        if merged:
            counts[result_idx] = counts.get(result_idx, 0) + merged
        stats.total_play_count = sum(counts.values())
        self.save(stats)
        self._update_date_stats_merge(media_path, cur_idx, nxt_idx, result_idx)

    def on_split(self, media_path: str, orig_idx: str, new_a: str, new_b: str) -> None:
        """Update stats after splitting a subtitle."""
        stats = self.load(media_path)
        counts = stats.subtitle_play_counts
        original = counts.pop(orig_idx, 0)
        front = (original + 1) // 2
        back = original // 2
        if front:
            counts[new_a] = counts.get(new_a, 0) + front
        if back:
            counts[new_b] = counts.get(new_b, 0) + back
        stats.total_play_count = sum(counts.values())
        self.save(stats)
        self._update_date_stats_split(media_path, orig_idx, new_a, new_b)

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
        self._date_path.parent.mkdir(parents=True, exist_ok=True)
        self._date_path.write_text(yaml.dump(data, allow_unicode=True, width=float("inf")), encoding="utf-8")

    def _increment_date_play(self, media_path: str, subtitle_index: str) -> None:
        today = date.today().isoformat()
        raw = self._load_date_raw()
        media_entry = raw.setdefault(media_path, {})
        day_entry = media_entry.setdefault(today, {"total_play_count": 0, "subtitle_play_counts": {}})
        day_entry["total_play_count"] = day_entry.get("total_play_count", 0) + 1
        sc = {str(k): v for k, v in day_entry.get("subtitle_play_counts", {}).items()}
        sc[subtitle_index] = sc.get(subtitle_index, 0) + 1
        day_entry["subtitle_play_counts"] = sc
        self._save_date_raw(raw)

    def _update_date_stats_merge(self, media_path: str, cur_idx: str, nxt_idx: str, result_idx: str) -> None:
        raw = self._load_date_raw()
        media_entry = raw.get(media_path)
        if not media_entry:
            return
        for day_entry in media_entry.values():
            sc: dict = {str(k): v for k, v in day_entry.get("subtitle_play_counts", {}).items()}
            merged = sc.pop(cur_idx, 0) + sc.pop(nxt_idx, 0)
            if merged:
                sc[result_idx] = sc.get(result_idx, 0) + merged
            day_entry["subtitle_play_counts"] = sc
            day_entry["total_play_count"] = sum(sc.values())
        self._save_date_raw(raw)

    def _update_date_stats_split(self, media_path: str, orig_idx: str, new_a: str, new_b: str) -> None:
        raw = self._load_date_raw()
        media_entry = raw.get(media_path)
        if not media_entry:
            return
        for day_entry in media_entry.values():
            sc: dict = {str(k): v for k, v in day_entry.get("subtitle_play_counts", {}).items()}
            original = sc.pop(orig_idx, 0)
            front = (original + 1) // 2
            back = original // 2
            if front:
                sc[new_a] = sc.get(new_a, 0) + front
            if back:
                sc[new_b] = sc.get(new_b, 0) + back
            day_entry["subtitle_play_counts"] = sc
            day_entry["total_play_count"] = sum(sc.values())
        self._save_date_raw(raw)

    def remap_indices(self, media_path: str, old_to_new: dict[str, str]) -> None:
        """Rename subtitle index keys in both segment and date stats."""
        if not old_to_new:
            return
        stats = self.load(media_path)
        new_counts: dict[str, int] = {}
        for idx, count in stats.subtitle_play_counts.items():
            new_idx = old_to_new.get(idx, idx)
            new_counts[new_idx] = new_counts.get(new_idx, 0) + count
        stats.subtitle_play_counts = new_counts
        stats.total_play_count = sum(new_counts.values())
        self.save(stats)
        raw = self._load_date_raw()
        media_entry = raw.get(media_path)
        if not media_entry:
            return
        for day_entry in media_entry.values():
            sc = {str(k): v for k, v in day_entry.get("subtitle_play_counts", {}).items()}
            new_sc: dict[str, int] = {}
            for idx, count in sc.items():
                new_idx = old_to_new.get(idx, idx)
                new_sc[new_idx] = new_sc.get(new_idx, 0) + count
            day_entry["subtitle_play_counts"] = new_sc
            day_entry["total_play_count"] = sum(new_sc.values())
        self._save_date_raw(raw)

    def _delete_date_entry(self, media_path: str) -> None:
        raw = self._load_date_raw()
        if media_path in raw:
            del raw[media_path]
            self._save_date_raw(raw)

    def load_date_stats(self, media_path: str) -> list[tuple[str, dict[str, int]]]:
        """Return list of (date_str, subtitle_play_counts) sorted newest first."""
        raw = self._load_date_raw()
        media_entry = raw.get(media_path, {})
        result = []
        for date_str, day_entry in media_entry.items():
            sc = {str(k): v for k, v in day_entry.get("subtitle_play_counts", {}).items()}
            result.append((date_str, sc))
        return sorted(result, key=lambda x: x[0], reverse=True)
