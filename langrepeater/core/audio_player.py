import contextlib
import os
import threading
import time
from abc import ABC, abstractmethod
from collections.abc import Callable
from pathlib import Path


@contextlib.contextmanager
def _suppress_stderr():
    """Redirect fd 2 to /dev/null to suppress C-level stderr (e.g. mpg123 id3.c warnings)."""
    devnull_fd = os.open(os.devnull, os.O_WRONLY)
    saved_fd = os.dup(2)
    os.dup2(devnull_fd, 2)
    os.close(devnull_fd)
    try:
        yield
    finally:
        os.dup2(saved_fd, 2)
        os.close(saved_fd)


class AudioPlayer(ABC):
    @abstractmethod
    def play_segment(self, path: str, start: float, end: float | None = None, on_complete: Callable | None = None) -> None:
        """Play audio from `start` seconds. If end is None, play to end of file without stopping."""

    @abstractmethod
    def stop(self) -> None:
        """Stop any currently playing audio."""

    @abstractmethod
    def toggle_pause(self) -> None:
        """Pause if playing, resume if paused."""

    @abstractmethod
    def is_playing(self) -> bool:
        """Return True if audio is currently playing (not paused, not stopped)."""

    @abstractmethod
    def get_position(self) -> float:
        """Return current playback position in seconds from file start."""


class PygameAudioPlayer(AudioPlayer):
    """mp3 player using pygame.mixer.music with seek support (no pydub needed)."""

    def __init__(self) -> None:
        import pygame
        pygame.mixer.init()
        self._pygame = pygame
        self._stop_timer: threading.Timer | None = None
        self._paused: bool = False
        self._remaining: float = 0.0
        self._play_start_time: float = 0.0
        self._on_complete: Callable | None = None
        self._start_pos: float = 0.0

    def play_segment(self, path: str, start: float, end: float | None = None, on_complete: Callable | None = None) -> None:
        self.stop()
        self._paused = False
        self._on_complete = on_complete
        self._start_pos = start
        music = self._pygame.mixer.music
        with _suppress_stderr():
            music.load(path)
            music.play(start=start)

        if end is not None:
            self._remaining = end - start
            self._play_start_time = time.monotonic()
            self._stop_timer = threading.Timer(self._remaining, self._on_segment_end)
            self._stop_timer.daemon = True
            self._stop_timer.start()

    def _on_segment_end(self) -> None:
        self._pygame.mixer.music.stop()
        self._paused = False
        self._remaining = 0.0
        if self._on_complete:
            self._on_complete()

    def toggle_pause(self) -> None:
        music = self._pygame.mixer.music
        if self._paused:
            # resume: restart timer with remaining time (only if a stop timer was in use)
            music.unpause()
            self._paused = False
            self._play_start_time = time.monotonic()
            if self._remaining > 0:
                self._stop_timer = threading.Timer(self._remaining, self._on_segment_end)
                self._stop_timer.daemon = True
                self._stop_timer.start()
        elif music.get_busy():
            # pause: cancel timer, save remaining time
            elapsed = time.monotonic() - self._play_start_time
            self._remaining = max(0.0, self._remaining - elapsed)
            if self._stop_timer:
                self._stop_timer.cancel()
                self._stop_timer = None
            music.pause()
            self._paused = True

    def is_playing(self) -> bool:
        return self._pygame.mixer.music.get_busy() and not self._paused

    def get_position(self) -> float:
        pos_ms = self._pygame.mixer.music.get_pos()
        if pos_ms < 0:
            return self._start_pos
        return self._start_pos + pos_ms / 1000

    def stop(self) -> None:
        if self._stop_timer is not None:
            self._stop_timer.cancel()
            self._stop_timer = None
        self._paused = False
        self._pygame.mixer.music.stop()


class VLCAudioPlayer(AudioPlayer):
    """mp4 audio-only player using python-vlc."""

    def __init__(self) -> None:
        import vlc
        self._vlc = vlc
        self._player = vlc.MediaPlayer()
        self._player.audio_set_mute(False)
        self._stop_timer: threading.Timer | None = None
        self._remaining: float = 0.0
        self._play_start_time: float = 0.0
        self._on_complete: Callable | None = None

    def play_segment(self, path: str, start: float, end: float | None = None, on_complete: Callable | None = None) -> None:
        self.stop()
        self._on_complete = on_complete

        media = self._vlc.Media(path)
        self._player.set_media(media)
        self._player.video_set_track(-1)
        self._player.play()
        self._player.set_time(int(start * 1000))

        if end is not None:
            self._remaining = end - start
            self._play_start_time = time.monotonic()
            self._stop_timer = threading.Timer(self._remaining, self._on_segment_end)
            self._stop_timer.daemon = True
            self._stop_timer.start()

    def _on_segment_end(self) -> None:
        self._player.stop()
        self._remaining = 0.0
        if self._on_complete:
            self._on_complete()

    def toggle_pause(self) -> None:
        import vlc
        if self._player.get_state() == vlc.State.Paused:
            # resume: restart timer with remaining time (only if a stop timer was in use)
            self._player.pause()
            self._play_start_time = time.monotonic()
            if self._remaining > 0:
                self._stop_timer = threading.Timer(self._remaining, self._on_segment_end)
                self._stop_timer.daemon = True
                self._stop_timer.start()
        elif self._player.get_state() == vlc.State.Playing:
            # pause: cancel timer, save remaining time
            elapsed = time.monotonic() - self._play_start_time
            self._remaining = max(0.0, self._remaining - elapsed)
            if self._stop_timer:
                self._stop_timer.cancel()
                self._stop_timer = None
            self._player.pause()

    def is_playing(self) -> bool:
        import vlc
        return self._player.get_state() == vlc.State.Playing

    def get_position(self) -> float:
        t = self._player.get_time()
        if t < 0:
            return 0.0
        return t / 1000

    def stop(self) -> None:
        if self._stop_timer is not None:
            self._stop_timer.cancel()
            self._stop_timer = None
        self._player.stop()


def create_player(media_path: str) -> AudioPlayer:
    ext = Path(media_path).suffix.lower()
    if ext == ".mp4":
        return VLCAudioPlayer()
    return PygameAudioPlayer()
