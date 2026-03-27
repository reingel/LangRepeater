import os
import select
from enum import Enum, auto


class Action(Enum):
    PLAY = auto()
    RESTART = auto()
    NEXT = auto()
    PREV = auto()
    QUIT = auto()
    SHIFT_START_EARLIER = auto()
    SHIFT_START_LATER = auto()
    SHIFT_END_EARLIER = auto()
    SHIFT_END_LATER = auto()
    MERGE = auto()
    SPLIT = auto()
    TOGGLE_SUBTITLE = auto()
    PRINT_STATS = auto()
    PRINT_DATE_STATS = auto()
    STATS_NEXT = auto()
    STATS_PREV = auto()
    HOME = auto()


_CHAR_MAP: dict[str, Action] = {
    " ": Action.PLAY,
    "s": Action.RESTART,
    "d": Action.NEXT,
    "a": Action.PREV,
    "q": Action.QUIT,
    "z": Action.SHIFT_START_EARLIER,
    "x": Action.SHIFT_START_LATER,
    ",": Action.SHIFT_END_EARLIER,
    ".": Action.SHIFT_END_LATER,
    "u": Action.MERGE,
    "i": Action.SPLIT,
    "v": Action.TOGGLE_SUBTITLE,
    "p": Action.PRINT_STATS,
    "0": Action.PRINT_DATE_STATS,
    "]": Action.STATS_NEXT,
    "[": Action.STATS_PREV,
}


def read_action(fd: int, timeout: float = 0.1) -> Action | None:
    """Read one key action from stdin fd (terminal must be in cbreak mode).

    Works only when the terminal window has focus, unlike pynput's global hook.
    """
    rlist, _, _ = select.select([fd], [], [], timeout)
    if not rlist:
        return None

    ch = os.read(fd, 1)

    if ch == b"\x1b":
        # Peek for escape sequence (arrow keys: ESC [ C / ESC [ D)
        rlist2, _, _ = select.select([fd], [], [], 0.05)
        if rlist2:
            ch2 = os.read(fd, 1)
            if ch2 == b"[":
                rlist3, _, _ = select.select([fd], [], [], 0.05)
                if rlist3:
                    ch3 = os.read(fd, 1)
                    if ch3 == b"A":
                        return Action.PREV   # up arrow
                    if ch3 == b"B":
                        return Action.NEXT   # down arrow
                    if ch3 == b"C":
                        return Action.NEXT   # right arrow
                    if ch3 == b"D":
                        return Action.PREV   # left arrow
        return Action.HOME  # bare ESC

    char = ch.decode("utf-8", errors="ignore").lower()
    return _CHAR_MAP.get(char)
