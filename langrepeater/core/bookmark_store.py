from pathlib import Path

import yaml

from .models import _index_key

_APP_DIR = Path.home() / ".langrepeater"
DEFAULT_PATH = _APP_DIR / "bookmark.yaml"

_BM_KEY = "bookmark"
_WT_KEY = "wrong_transcription"


class BookmarkStore:
    def __init__(self, path: Path = DEFAULT_PATH):
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
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(
            yaml.dump(data, allow_unicode=True, width=float("inf")),
            encoding="utf-8",
        )

    def _get_section(self, data: dict, media_path: str, key: str) -> list[str]:
        """미디어 항목에서 key 섹션의 인덱스 리스트 반환. 구버전(리스트) 호환."""
        entry = data.get(media_path, {})
        if isinstance(entry, list):
            # 구버전: 리스트 전체가 bookmark
            return [str(x) for x in entry] if key == _BM_KEY else []
        if isinstance(entry, dict):
            return [str(x) for x in entry.get(key, [])]
        return []

    def _set_section(self, data: dict, media_path: str, key: str, indices: list[str]) -> None:
        entry = data.get(media_path)
        if isinstance(entry, list):
            # 구버전 → 새 구조로 전환
            old_bm = [str(x) for x in entry]
            entry = {_BM_KEY: old_bm, _WT_KEY: []}
        elif not isinstance(entry, dict):
            entry = {_BM_KEY: [], _WT_KEY: []}
        entry[key] = indices
        data[media_path] = entry

    # ── Bookmark ───────────────────────────────────────────────────────────────

    def load(self, media_path: str) -> set[str]:
        data = self._load_all()
        return set(self._get_section(data, media_path, _BM_KEY))

    def add(self, media_path: str, sub_index: str) -> None:
        data = self._load_all()
        indices = self._get_section(data, media_path, _BM_KEY)
        if sub_index not in indices:
            indices.append(sub_index)
            indices.sort(key=_index_key)
        self._set_section(data, media_path, _BM_KEY, indices)
        self._save_all(data)

    def remove(self, media_path: str, sub_index: str) -> None:
        data = self._load_all()
        indices = self._get_section(data, media_path, _BM_KEY)
        if sub_index in indices:
            indices.remove(sub_index)
        self._set_section(data, media_path, _BM_KEY, indices)
        self._save_all(data)

    def toggle(self, media_path: str, sub_index: str) -> bool:
        data = self._load_all()
        indices = self._get_section(data, media_path, _BM_KEY)
        if sub_index in indices:
            indices.remove(sub_index)
            added = False
        else:
            indices.append(sub_index)
            indices.sort(key=_index_key)
            added = True
        self._set_section(data, media_path, _BM_KEY, indices)
        self._save_all(data)
        return added

    # ── Wrong transcription ────────────────────────────────────────────────────

    def load_wrong(self, media_path: str) -> set[str]:
        data = self._load_all()
        return set(self._get_section(data, media_path, _WT_KEY))

    def add_wrong(self, media_path: str, sub_index: str) -> None:
        data = self._load_all()
        indices = self._get_section(data, media_path, _WT_KEY)
        if sub_index not in indices:
            indices.append(sub_index)
            indices.sort(key=_index_key)
        self._set_section(data, media_path, _WT_KEY, indices)
        self._save_all(data)

    def remove_wrong(self, media_path: str, sub_index: str) -> None:
        data = self._load_all()
        indices = self._get_section(data, media_path, _WT_KEY)
        if sub_index in indices:
            indices.remove(sub_index)
        self._set_section(data, media_path, _WT_KEY, indices)
        self._save_all(data)

    # ── Remap (split/merge 후 인덱스 갱신) ────────────────────────────────────

    def remap_indices(self, media_path: str, old_to_new: dict[str, str]) -> None:
        if not old_to_new:
            return
        data = self._load_all()
        for key in (_BM_KEY, _WT_KEY):
            indices = self._get_section(data, media_path, key)
            new_indices = [old_to_new.get(idx, idx) for idx in indices]
            seen: set[str] = set()
            deduped = []
            for idx in new_indices:
                if idx not in seen:
                    seen.add(idx)
                    deduped.append(idx)
            deduped.sort(key=_index_key)
            self._set_section(data, media_path, key, deduped)
        self._save_all(data)
