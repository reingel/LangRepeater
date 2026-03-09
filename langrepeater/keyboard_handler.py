from enum import Enum, auto
from typing import Callable

from pynput import keyboard


class Action(Enum):
    PLAY = auto()
    NEXT = auto()
    PREV = auto()
    QUIT = auto()
    SHIFT_START_EARLIER = auto()
    SHIFT_START_LATER = auto()
    SHIFT_END_EARLIER = auto()
    SHIFT_END_LATER = auto()


_KEY_MAP: dict[str, Action] = {
    "s": Action.PLAY,
    "d": Action.NEXT,
    "a": Action.PREV,
    "q": Action.QUIT,
    "z": Action.SHIFT_START_EARLIER,
    "x": Action.SHIFT_START_LATER,
    "n": Action.SHIFT_END_EARLIER,
    "m": Action.SHIFT_END_LATER,
}


class KeyboardHandler:
    def __init__(self) -> None:
        self._listener: keyboard.Listener | None = None

    def start(self, callback: Callable[[Action], None]) -> None:
        def on_press(key: keyboard.Key | keyboard.KeyCode | None) -> None:
            action = _resolve(key)
            if action is not None:
                callback(action)

        self._listener = keyboard.Listener(on_press=on_press)
        self._listener.daemon = True
        self._listener.start()

    def stop(self) -> None:
        if self._listener is not None:
            self._listener.stop()
            self._listener = None


def _resolve(key: keyboard.Key | keyboard.KeyCode | None) -> Action | None:
    if key is None:
        return None

    # special keys
    if key == keyboard.Key.space:
        return Action.PLAY
    if key == keyboard.Key.right:
        return Action.NEXT
    if key == keyboard.Key.left:
        return Action.PREV
    if key == keyboard.Key.esc:
        return Action.QUIT

    # character keys
    if hasattr(key, "char") and key.char is not None:
        return _KEY_MAP.get(key.char.lower())

    return None
