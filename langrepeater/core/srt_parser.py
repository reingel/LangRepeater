import datetime
import json
import re
from pathlib import Path

import srt
import yaml

from .models import Subtitle, WordTimestamp


def _strip_font_tags(text: str) -> str:
    """Remove <font ...>...</font> tags, keeping inner text."""
    return re.sub(r'<font[^>]*>(.*?)</font>', r'\1', text, flags=re.DOTALL).strip()


def _prefix_word_count(text: str) -> int:
    """Return number of whitespace-delimited tokens before the first <font> tag.

    Returns -1 if no font tag is found.
    """
    m = re.search(r'<font', text)
    if not m:
        return -1
    prefix = text[:m.start()].strip()
    return len(prefix.split()) if prefix else 0


def _words_yaml_path(srt_path: str) -> Path:
    return Path(srt_path).with_name(Path(srt_path).stem + "-words.yaml")


def _words_json_path(srt_path: str) -> Path:
    p = Path(srt_path)
    return p.parent / (p.stem + ".mp3.json")


def _word_srt_path(srt_path: str) -> Path:
    p = Path(srt_path)
    return p.with_name(p.stem + "-word" + p.suffix)


class SRTParser:
    _MARGIN = -0.3  # seconds of padding added to each sentence boundary

    def save(self, path: str, subtitles: list[Subtitle]) -> None:
        srt_subtitles = [
            srt.Subtitle(
                index=sub.index,
                start=datetime.timedelta(seconds=sub.start),
                end=datetime.timedelta(seconds=sub.end),
                content=sub.text,
            )
            for sub in subtitles
        ]
        with open(path, "w", encoding="utf-8") as f:
            f.write(srt.compose(srt_subtitles))

    def load(self, path: str) -> list[Subtitle]:
        if not Path(path).exists():
            json_path = _words_json_path(path)
            if json_path.exists():
                all_wts = self.load_words_json(path)
                subtitles = self.subtitles_from_words(all_wts)
                self.save(path, subtitles)
                return subtitles
            yaml_path = _words_yaml_path(path)
            if yaml_path.exists():
                all_wts = self.load_words_yaml(path)
                subtitles = self.subtitles_from_words(all_wts)
                self.save(path, subtitles)
                return subtitles
            raise FileNotFoundError(f"SRT file not found: {path}")

        with open(path, encoding="utf-8") as f:
            content = f.read()

        raw_subs = list(srt.parse(content))

        if self._is_word_level(raw_subs):
            Path(path).rename(_word_srt_path(path))
            all_wts = self._collect_words(raw_subs)
            self.save_words_yaml(path, all_wts)
            subtitles = self.subtitles_from_words(all_wts)
            self.save(path, subtitles)
            return subtitles

        # Normal sentence-level SRT
        subtitles = []
        for sub in raw_subs:
            start = sub.start.total_seconds()
            end = sub.end.total_seconds()
            if end <= start:
                continue
            subtitles.append(Subtitle(
                index=sub.index,
                start=start,
                end=end,
                text=sub.content.strip(),
            ))
        return sorted(subtitles, key=lambda s: s.index)

    def _is_word_level(self, raw_subs: list) -> bool:
        """Return True if the SRT file uses word-by-word highlighting format."""
        if len(raw_subs) < 3:
            return False
        tagged = sum(1 for s in raw_subs if '<font' in s.content)
        return tagged > len(raw_subs) * 0.5

    def _collect_words(self, raw_subs: list) -> list[WordTimestamp]:
        """Extract flat word list from word-level SRT (one entry per word)."""
        word_groups: list[list] = []
        for sub in raw_subs:
            base = _strip_font_tags(sub.content)
            if not base:
                continue
            if word_groups and _strip_font_tags(word_groups[-1][0].content) == base:
                word_groups[-1].append(sub)
            else:
                word_groups.append([sub])

        all_wts: list[WordTimestamp] = []
        for group in word_groups:
            base_text = _strip_font_tags(group[0].content)
            sentence_words = base_text.split()
            for entry in group:
                idx = _prefix_word_count(entry.content)
                if 0 <= idx < len(sentence_words):
                    all_wts.append(WordTimestamp(
                        word=sentence_words[idx],
                        start=entry.start.total_seconds(),
                        end=entry.end.total_seconds(),
                    ))
        return all_wts

    def subtitles_from_words(self, all_wts: list[WordTimestamp]) -> list[Subtitle]:
        """Build sentence-level Subtitles from flat word list.

        Groups words into sentences at .?! boundaries.
        Boundaries between sentences use midpoint ± margin.
        """
        if not all_wts:
            return []

        # Group words into sentences by punctuation
        sentences: list[list[WordTimestamp]] = []
        current: list[WordTimestamp] = []
        for wt in all_wts:
            current.append(wt)
            if re.search(r'[.?!]\s*$', wt.word):
                sentences.append(current)
                current = []
        if current:
            sentences.append(current)

        # raw = (first_word_start, last_word_end, text, words)
        raw = [
            (s[0].start, s[-1].end, " ".join(wt.word for wt in s), s)
            for s in sentences
        ]

        subtitles: list[Subtitle] = []
        for i, (raw_start, raw_end, text, _) in enumerate(raw):
            if i == 0:
                start = max(0.0, raw_start - self._MARGIN)
            else:
                start = (raw[i - 1][1] + raw_start) / 2 + self._MARGIN

            if i == len(raw) - 1:
                end = raw_end + self._MARGIN
            else:
                end = (raw_end + raw[i + 1][0]) / 2 + self._MARGIN

            if end <= start:
                continue

            subtitles.append(Subtitle(
                index=i + 1,
                start=start,
                end=end,
                text=text,
            ))

        return subtitles

    def save_words_yaml(self, srt_path: str, all_wts: list[WordTimestamp]) -> None:
        """Save flat word list to {stem}-words.yaml."""
        data = [
            {"start": wt.start, "word": wt.word, "end": wt.end}
            for wt in all_wts
        ]
        with open(_words_yaml_path(srt_path), "w", encoding="utf-8") as f:
            yaml.dump(data, f, allow_unicode=True, sort_keys=False)

    def load_words_yaml(self, srt_path: str) -> list[WordTimestamp]:
        """Load flat word list from {stem}-words.yaml. Returns [] if not found."""
        yaml_path = _words_yaml_path(srt_path)
        if not yaml_path.exists():
            return []
        with open(yaml_path, encoding="utf-8") as f:
            data = yaml.safe_load(f) or []
        return [
            WordTimestamp(word=w["word"], start=w["start"], end=w["end"])
            for w in data
        ]

    def load_words_json(self, srt_path: str) -> list[WordTimestamp]:
        """Load flat word list from whisper-cli JSON ({stem}.mp3.json). Returns [] if not found."""
        json_path = _words_json_path(srt_path)
        if not json_path.exists():
            return []
        with open(json_path, encoding="utf-8") as f:
            data = json.load(f)
        result: list[WordTimestamp] = []
        for seg in data.get("transcription", []):
            text = seg.get("text", "")
            stripped = text.strip().strip('"')
            if not stripped or stripped.startswith("["):
                continue
            offsets = seg.get("offsets", {})
            start = offsets.get("from", 0) / 1000.0
            end = offsets.get("to", 0) / 1000.0
            result.append(WordTimestamp(word=stripped, start=start, end=end))
        return result
