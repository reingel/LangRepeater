from pathlib import Path

import yaml

from .models import _index_key

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

    def load(self, media_path: str) -> set[str]:
        """Return set of bookmarked subtitle indices (as strings) for the given media."""
        data = self._load_all()
        indices = data.get(media_path, [])
        return {str(x) for x in indices} if isinstance(indices, list) else set()

    def add(self, media_path: str, sub_index: str) -> None:
        data = self._load_all()
        indices: list[str] = [str(x) for x in data.get(media_path, [])]
        if sub_index not in indices:
            indices.append(sub_index)
            indices.sort(key=_index_key)
        data[media_path] = indices
        self._save_all(data)

    def remove(self, media_path: str, sub_index: str) -> None:
        data = self._load_all()
        indices: list[str] = [str(x) for x in data.get(media_path, [])]
        if sub_index in indices:
            indices.remove(sub_index)
        data[media_path] = indices
        self._save_all(data)

    def toggle(self, media_path: str, sub_index: str) -> bool:
        """Toggle bookmark. Returns True if added, False if removed."""
        data = self._load_all()
        indices: list[str] = [str(x) for x in data.get(media_path, [])]
        if sub_index in indices:
            indices.remove(sub_index)
            added = False
        else:
            indices.append(sub_index)
            indices.sort(key=_index_key)
            added = True
        data[media_path] = indices
        self._save_all(data)
        return added
