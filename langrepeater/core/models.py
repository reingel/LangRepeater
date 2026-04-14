from dataclasses import dataclass, field


def _index_key(idx: str) -> tuple[int, ...]:
    """Sort/compare key for subtitle index strings.

    '45'   → (45,)
    '45-1' → (45, 1)
    '45-1-2' → (45, 1, 2)
    """
    try:
        return tuple(int(p) for p in idx.split('-'))
    except ValueError:
        return (0,)


def _split_indices(idx: str) -> tuple[str, str]:
    """Return child indexes when splitting idx.

    '45'   → ('45-1', '45-2')
    '45-1' → ('45-1-1', '45-1-2')
    """
    return (idx + "-1", idx + "-2")


def _merged_index(a: str, b: str) -> str:
    """Return index for the subtitle produced by merging a and b.

    '45-1' + '45-2' → '45'  (strip suffix when bases match)
    '45'   + '46'   → '45'  (keep first)
    """
    a_parts = a.split('-')
    b_parts = b.split('-')
    if a_parts[0] == b_parts[0] and len(a_parts) > 1:
        return a_parts[0]
    return a


@dataclass
class WordTimestamp:
    word: str
    start: float  # seconds from start of media
    end: float    # seconds from start of media


@dataclass
class Subtitle:
    index: str    # display index, e.g. "1", "45-1", "45-2"
    start: float  # seconds from start of media
    end: float    # seconds from start of media
    text: str
    word_timestamps: list[WordTimestamp] = field(default_factory=list)


@dataclass
class Session:
    media_path: str
    srt_path: str
    current_index: int  # 0-based index into subtitle list
    total_segments: int = 0


@dataclass
class SessionStats:
    media_path: str
    total_play_count: int = 0
    subtitle_play_counts: dict[str, int] = field(default_factory=dict)
    progress_pct: float = 0.0
