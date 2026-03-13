import threading
import time
from abc import ABC, abstractmethod
from collections.abc import Callable
from pathlib import Path


class AudioPlayer(ABC):
    @abstractmethod
    def play_segment(self, path: str, start: float, end: float, on_complete: Callable | None = None) -> None:
        """Play audio from `start` to `end` seconds. on_complete called only on natural finish."""

    @abstractmethod
    def stop(self) -> None:
        """Stop any currently playing audio."""

    @abstractmethod
    def toggle_pause(self) -> None:
        """Pause if playing, resume if paused."""

    @abstractmethod
    def is_playing(self) -> bool:
        """Return True if audio is currently playing (not paused, not stopped)."""


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

    def play_segment(self, path: str, start: float, end: float, on_complete: Callable | None = None) -> None:
        self.stop()
        self._paused = False
        self._on_complete = on_complete
        music = self._pygame.mixer.music
        music.load(path)
        music.play(start=start)

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
            # resume: restart timer with remaining time
            music.unpause()
            self._paused = False
            self._play_start_time = time.monotonic()
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

    def play_segment(self, path: str, start: float, end: float, on_complete: Callable | None = None) -> None:
        self.stop()
        self._on_complete = on_complete

        media = self._vlc.Media(path)
        self._player.set_media(media)
        self._player.video_set_track(-1)
        self._player.play()
        self._player.set_time(int(start * 1000))

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
            # resume: restart timer with remaining time
            self._player.pause()
            self._play_start_time = time.monotonic()
            self._stop_timer = threading.Timer(self._remaining, self._player.stop)
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
