from pathlib import Path


MEDIA_EXTENSIONS = {".mp3", ".mp4"}
SRT_EXTENSIONS = {".srt"}


class FileFinder:
    def find_media(self, directory: str) -> list[str]:
        return self._find(directory, MEDIA_EXTENSIONS)

    def find_srt(self, directory: str) -> list[str]:
        return self._find(directory, SRT_EXTENSIONS)

    def _find(self, directory: str, extensions: set[str]) -> list[str]:
        base = Path(directory)
        if not base.exists() or not base.is_dir():
            return []
        results = [
            str(p.resolve())
            for p in base.iterdir()
            if p.is_file() and p.suffix.lower() in extensions
        ]
        return sorted(results)
