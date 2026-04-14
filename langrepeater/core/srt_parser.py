import json
import re
from pathlib import Path

import yaml

from .models import Subtitle, WordTimestamp, _index_key

_CAPITAL_LETTERS_PATH = Path(__file__).parent.parent / "capital_letters.json"
_ABBREVIATIONS_PATH = Path(__file__).parent.parent / "abbreviations.json"


def _load_capital_letters() -> set[str]:
    if _CAPITAL_LETTERS_PATH.exists():
        with open(_CAPITAL_LETTERS_PATH, encoding="utf-8") as f:
            return set(json.load(f))
    return {"I"}


def _load_abbreviations() -> set[str]:
    if _ABBREVIATIONS_PATH.exists():
        with open(_ABBREVIATIONS_PATH, encoding="utf-8") as f:
            return set(json.load(f))
    return set()


_CAPITAL_LETTERS: set[str] = _load_capital_letters()
_ABBREVIATIONS: set[str] = _load_abbreviations()


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


# ---------------------------------------------------------------------------
# Custom SRT parse / format helpers (supports non-integer indexes like "45-1")
# ---------------------------------------------------------------------------

_TIME_RE = re.compile(r'(\d+):(\d+):(\d+)[,\.](\d+)')


def _parse_time(s: str) -> float:
    m = _TIME_RE.match(s.strip())
    if not m:
        return 0.0
    h, mn, sec, ms = int(m[1]), int(m[2]), int(m[3]), int(m[4])
    return h * 3600 + mn * 60 + sec + ms / 1000.0


def _format_time(seconds: float) -> str:
    ms = round(seconds * 1000)
    h = ms // 3_600_000; ms %= 3_600_000
    m = ms // 60_000; ms %= 60_000
    s = ms // 1000; ms %= 1000
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


_TS_LINE_RE = re.compile(
    r'(\d+:\d+:\d+[,\.]\d+)\s*-->\s*(\d+:\d+:\d+[,\.]\d+)'
)


def _parse_srt_blocks(content: str) -> list[tuple[str, float, float, str]]:
    """Parse SRT content into (index_str, start_sec, end_sec, text) tuples.

    Accepts both integer and non-integer (e.g. '45-1') index lines.
    """
    result: list[tuple[str, float, float, str]] = []
    lines = content.replace('\r\n', '\n').replace('\r', '\n').split('\n')
    i = 0
    while i < len(lines):
        # skip blank lines
        while i < len(lines) and not lines[i].strip():
            i += 1
        if i >= len(lines):
            break
        index_str = lines[i].strip()
        i += 1
        if i >= len(lines):
            break
        # timestamp line
        m = _TS_LINE_RE.match(lines[i].strip())
        i += 1
        if not m:
            continue
        start = _parse_time(m.group(1))
        end = _parse_time(m.group(2))
        # content lines until blank
        content_lines: list[str] = []
        while i < len(lines) and lines[i].strip():
            content_lines.append(lines[i])
            i += 1
        text = '\n'.join(content_lines).strip()
        result.append((index_str, start, end, text))
    return result


class SRTParser:
    _MARGIN = 0.0  # seconds of padding added to each sentence boundary

    def save(self, path: str, subtitles: list[Subtitle]) -> None:
        with open(path, "w", encoding="utf-8") as f:
            for sub in subtitles:
                f.write(f"{sub.index}\n")
                f.write(f"{_format_time(sub.start)} --> {_format_time(sub.end)}\n")
                f.write(f"{sub.text}\n\n")

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

        blocks = _parse_srt_blocks(content)

        if self._is_word_level_blocks(blocks):
            Path(path).rename(_word_srt_path(path))
            all_wts = self._collect_words_from_blocks(blocks)
            self.save_words_yaml(path, all_wts)
            subtitles = self.subtitles_from_words(all_wts)
            self.save(path, subtitles)
            return subtitles

        # Normal sentence-level SRT
        subtitles = []
        for index_str, start, end, text in blocks:
            if end <= start:
                continue
            subtitles.append(Subtitle(
                index=index_str,
                start=start,
                end=end,
                text=text,
            ))
        return sorted(subtitles, key=lambda s: _index_key(s.index))

    def _is_word_level_blocks(self, blocks: list[tuple[str, float, float, str]]) -> bool:
        if len(blocks) < 3:
            return False
        tagged = sum(1 for _, _, _, text in blocks if '<font' in text)
        return tagged > len(blocks) * 0.5

    def _collect_words_from_blocks(self, blocks: list[tuple[str, float, float, str]]) -> list[WordTimestamp]:
        """Extract flat word list from word-level SRT blocks."""
        # Reconstruct srt-like objects for compatibility with existing logic
        class _FakeSub:
            def __init__(self, index_str, start, end, content):
                self.index = index_str
                self.start_s = start
                self.end_s = end
                self.content = content

        raw_subs = [_FakeSub(idx, s, e, t) for idx, s, e, t in blocks]

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
                        start=entry.start_s,
                        end=entry.end_s,
                    ))
        return all_wts

    def subtitles_from_words(self, all_wts: list[WordTimestamp]) -> list[Subtitle]:
        """Build sentence-level Subtitles from flat word list."""
        if not all_wts:
            return []

        sentences: list[list[WordTimestamp]] = []
        current: list[WordTimestamp] = []
        for wt in all_wts:
            current.append(wt)
            if re.search(r'[.?!]\s*$', wt.word) and wt.word.strip() not in _ABBREVIATIONS:
                sentences.append(current)
                current = []
        if current:
            sentences.append(current)

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
                index=str(i + 1),
                start=start,
                end=end,
                text=text,
            ))

        return subtitles

    def save_words_yaml(self, srt_path: str, all_wts: list[WordTimestamp]) -> None:
        data = [
            {"start": wt.start, "word": wt.word, "end": wt.end}
            for wt in all_wts
        ]
        with open(_words_yaml_path(srt_path), "w", encoding="utf-8") as f:
            yaml.dump(data, f, allow_unicode=True, sort_keys=False)

    def load_words_yaml(self, srt_path: str) -> list[WordTimestamp]:
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
        json_path = _words_json_path(srt_path)
        if not json_path.exists():
            return []
        with open(json_path, encoding="utf-8", errors="replace") as f:
            data = json.load(f)
        result: list[WordTimestamp] = []
        for seg in data.get("transcription", []):
            text = seg.get("text", "")
            text_stripped = text.strip()
            had_leading_quote = text_stripped.startswith('"')
            stripped = text_stripped.strip('"')
            if not stripped or stripped.startswith("["):
                continue
            if had_leading_quote and stripped and stripped[0].isupper():
                first_word = re.split(r"[\s']", stripped)[0]
                if first_word not in _CAPITAL_LETTERS:
                    stripped = stripped[0].lower() + stripped[1:]
            offsets = seg.get("offsets", {})
            start = offsets.get("from", 0) / 1000.0
            end = offsets.get("to", 0) / 1000.0
            result.append(WordTimestamp(word=stripped, start=start, end=end))
        return result
