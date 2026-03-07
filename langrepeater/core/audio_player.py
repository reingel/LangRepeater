import threading
from abc import ABC, abstractmethod
from pathlib import Path


class AudioPlayer(ABC):
    @abstractmethod
    def play_segment(self, path: str, start: float, end: float) -> None:
        """Play audio from `start` to `end` seconds."""

    @abstractmethod
    def stop(self) -> None:
        """Stop any currently playing audio."""


class PygameAudioPlayer(AudioPlayer):
    """mp3 player using pygame.mixer.music with seek support (no pydub needed)."""

    def __init__(self) -> None:
        import pygame
        pygame.mixer.init()
        self._pygame = pygame
        self._stop_timer: threading.Timer | None = None

    def play_segment(self, path: str, start: float, end: float) -> None:
        self.stop()
        music = self._pygame.mixer.music
        music.load(path)
        music.play(start=start)

        duration = end - start
        self._stop_timer = threading.Timer(duration, music.stop)
        self._stop_timer.daemon = True
        self._stop_timer.start()

    def stop(self) -> None:
        if self._stop_timer is not None:
            self._stop_timer.cancel()
            self._stop_timer = None
        self._pygame.mixer.music.stop()


class VLCAudioPlayer(AudioPlayer):
    """mp4 audio-only player using python-vlc."""

    def __init__(self) -> None:
        import vlc
        self._vlc = vlc
        self._player = vlc.MediaPlayer()
        self._player.audio_set_mute(False)
        self._stop_timer: threading.Timer | None = None

    def play_segment(self, path: str, start: float, end: float) -> None:
        self.stop()

        media = self._vlc.Media(path)
        self._player.set_media(media)
        # disable video track
        self._player.video_set_track(-1)
        self._player.play()
        # seek to start position
        self._player.set_time(int(start * 1000))

        duration = end - start
        self._stop_timer = threading.Timer(duration, self._player.stop)
        self._stop_timer.daemon = True
        self._stop_timer.start()

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
