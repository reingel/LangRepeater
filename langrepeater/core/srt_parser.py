import srt

from .models import Subtitle


class SRTParser:
    def load(self, path: str) -> list[Subtitle]:
        with open(path, encoding="utf-8") as f:
            content = f.read()

        subtitles = []
        for sub in srt.parse(content):
            start = sub.start.total_seconds()
            end = sub.end.total_seconds()
            if end <= start:
                continue  # skip zero-duration or invalid entries
            subtitles.append(Subtitle(
                index=sub.index,
                start=start,
                end=end,
                text=sub.content.strip(),
            ))

        return sorted(subtitles, key=lambda s: s.index)
