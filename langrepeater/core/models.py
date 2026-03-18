from dataclasses import dataclass, field


@dataclass
class Subtitle:
    index: int    # 1-based
    start: float  # seconds from start of media
    end: float    # seconds from start of media
    text: str


@dataclass
class Session:
    media_path: str
    srt_path: str
    current_index: int  # 0-based index into subtitle list


@dataclass
class SessionStats:
    media_path: str
    total_play_count: int = 0
    subtitle_play_counts: dict[int, int] = field(default_factory=dict)
    progress_pct: float = 0.0
