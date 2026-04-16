from pathlib import Path

import yaml

DEFAULT_PATH = "settings.yaml"
_DEFAULTS: dict = {
    "de_esser_reduction_db": 8.0,
}


class SettingsStore:
    def __init__(self, path: str = DEFAULT_PATH):
        self.path = Path(path)
        self._data: dict = dict(_DEFAULTS)

    def load(self) -> None:
        if not self.path.exists():
            return
        try:
            data = yaml.safe_load(self.path.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                self._data.update(data)
        except Exception:
            pass

    def _save(self) -> None:
        try:
            self.path.write_text(yaml.dump(self._data, allow_unicode=True), encoding="utf-8")
        except Exception:
            pass

    @property
    def de_esser_reduction_db(self) -> float:
        return float(self._data.get("de_esser_reduction_db", _DEFAULTS["de_esser_reduction_db"]))

    @de_esser_reduction_db.setter
    def de_esser_reduction_db(self, value: float) -> None:
        self._data["de_esser_reduction_db"] = round(value, 1)
        self._save()
