from pathlib import Path

import yaml

DEFAULT_PATH = "bookmark.yaml"


class BookmarkStore:
    def __init__(self, path: str = DEFAULT_PATH):
        self.path = Path(path)

    def _load_all(self) -> dict:
        if not self.path.exists():
            return {}
        try:
            data = yaml.safe_load(self.path.read_text(encoding="utf-8"))
            return data if isinstance(data, dict) else {}
        except Exception:
            return {}

    def _save_all(self, data: dict) -> None:
        self.path.write_text(
            yaml.dump(data, allow_unicode=True, width=float("inf")),
            encoding="utf-8",
        )

    def load(self, media_path: str) -> set[int]:
        """Return set of bookmarked 1-based subtitle indices for the given media."""
        data = self._load_all()
        indices = data.get(media_path, [])
        return set(indices) if isinstance(indices, list) else set()

    def add(self, media_path: str, sub_index: int) -> None:
        """Add a 1-based subtitle index to bookmarks."""
        data = self._load_all()
        indices: list[int] = data.get(media_path, [])
        if sub_index not in indices:
            indices.append(sub_index)
            indices.sort()
        data[media_path] = indices
        self._save_all(data)

    def remove(self, media_path: str, sub_index: int) -> None:
        """Remove a 1-based subtitle index from bookmarks."""
        data = self._load_all()
        indices: list[int] = data.get(media_path, [])
        if sub_index in indices:
            indices.remove(sub_index)
        data[media_path] = indices
        self._save_all(data)

    def toggle(self, media_path: str, sub_index: int) -> bool:
        """Toggle bookmark. Returns True if added, False if removed."""
        data = self._load_all()
        indices: list[int] = data.get(media_path, [])
        if sub_index in indices:
            indices.remove(sub_index)
            added = False
        else:
            indices.append(sub_index)
            indices.sort()
            added = True
        data[media_path] = indices
        self._save_all(data)
        return added
