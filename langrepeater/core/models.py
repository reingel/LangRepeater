from dataclasses import dataclass, field


@dataclass
class WordTimestamp:
    word: str
    start: float  # seconds from start of media
    end: float    # seconds from start of media


@dataclass
class Subtitle:
    index: int    # 1-based
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
    subtitle_play_counts: dict[int, int] = field(default_factory=dict)
    progress_pct: float = 0.0
