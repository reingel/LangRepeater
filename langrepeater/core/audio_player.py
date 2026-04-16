import contextlib
import os
import tempfile
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
    """mp3 player using pygame.mixer.music with seek support.

    de_esser=True 시 ffmpeg으로 치찰음 대역(cutoff_hz 이상)을 reduction_db만큼 감쇄한다.
    """

    def __init__(
        self,
        de_esser: bool = True,
        de_esser_cutoff_hz: int = 7000,
        de_esser_reduction_db: float = 8.0,
    ) -> None:
        import pygame
        pygame.mixer.init()
        self._pygame = pygame
        self._stop_timer: threading.Timer | None = None
        self._paused: bool = False
        self._remaining: float = 0.0
        self._play_start_time: float = 0.0
        self._paused_offset: float = 0.0  # cumulative play time before current play period
        self._on_complete: Callable | None = None
        self._start_pos: float = 0.0
        self._de_esser = de_esser
        self._de_esser_cutoff_hz = de_esser_cutoff_hz
        self._de_esser_reduction_db = de_esser_reduction_db
        self._temp_file: str | None = None

    def _cleanup_temp(self) -> None:
        if self._temp_file:
            try:
                os.unlink(self._temp_file)
            except OSError:
                pass
            self._temp_file = None

    def _process_de_esser(self, path: str, start: float, end: float | None) -> tuple[str, float | None]:
        """ffmpeg으로 치찰음 제거 후 임시 WAV 파일 경로와 재생 길이(초)를 반환한다."""
        import subprocess

        fd, tmp_path = tempfile.mkstemp(suffix=".wav")
        os.close(fd)

        duration: float | None = end - start if end is not None else None

        # ffmpeg equalizer 필터: high-shelf로 치찰음 대역 감쇄
        # f=cutoff, t=h(high-shelf), width=bandwith, g=gain(dB, 음수=감쇄)
        af = (
            f"equalizer=f={self._de_esser_cutoff_hz}:t=h"
            f":width={self._de_esser_cutoff_hz}:g=-{self._de_esser_reduction_db}"
        )

        cmd = ["ffmpeg", "-y", "-ss", str(start), "-i", path]
        if end is not None:
            cmd += ["-t", str(duration)]
        cmd += ["-af", af, "-ar", "44100", tmp_path]

        subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
        return tmp_path, duration

    def play_segment(self, path: str, start: float, end: float | None = None, on_complete: Callable | None = None) -> None:
        self.stop()
        self._paused = False
        self._paused_offset = 0.0
        self._on_complete = on_complete
        self._start_pos = start

        music = self._pygame.mixer.music

        if self._de_esser:
            self._cleanup_temp()
            tmp_path, duration = self._process_de_esser(path, start, end)
            self._temp_file = tmp_path
            with _suppress_stderr():
                music.load(tmp_path)
                music.play(start=0)
            self._play_start_time = time.monotonic()
            if duration is not None:
                self._remaining = duration
                self._stop_timer = threading.Timer(self._remaining, self._on_segment_end)
                self._stop_timer.daemon = True
                self._stop_timer.start()
        else:
            with _suppress_stderr():
                music.load(path)
                music.play(start=start)
            self._play_start_time = time.monotonic()
            if end is not None:
                self._remaining = end - start
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
            # resume: restart a fresh play period from current paused position
            music.unpause()
            self._paused = False
            self._play_start_time = time.monotonic()
            if self._remaining > 0:
                self._stop_timer = threading.Timer(self._remaining, self._on_segment_end)
                self._stop_timer.daemon = True
                self._stop_timer.start()
        elif music.get_busy():
            # pause: accumulate elapsed into _paused_offset, reduce remaining
            elapsed = time.monotonic() - self._play_start_time
            self._paused_offset += elapsed
            self._remaining = max(0.0, self._remaining - elapsed)
            if self._stop_timer:
                self._stop_timer.cancel()
                self._stop_timer = None
            music.pause()
            self._paused = True

    def is_playing(self) -> bool:
        return self._pygame.mixer.music.get_busy() and not self._paused

    def get_position(self) -> float:
        if self._paused:
            return self._start_pos + self._paused_offset
        if not self._pygame.mixer.music.get_busy():
            return self._start_pos + self._paused_offset
        return self._start_pos + self._paused_offset + (time.monotonic() - self._play_start_time)

    def stop(self) -> None:
        if self._stop_timer is not None:
            self._stop_timer.cancel()
            self._stop_timer = None
        self._paused = False
        self._pygame.mixer.music.stop()
        self._cleanup_temp()


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
        self._paused_offset: float = 0.0  # cumulative play time before current play period
        self._on_complete: Callable | None = None
        self._start_pos: float = 0.0
        self._paused: bool = False

    def play_segment(self, path: str, start: float, end: float | None = None, on_complete: Callable | None = None) -> None:
        self.stop()
        self._paused = False
        self._paused_offset = 0.0
        self._on_complete = on_complete
        self._start_pos = start

        media = self._vlc.Media(path)
        self._player.set_media(media)
        self._player.video_set_track(-1)
        self._player.play()

        # :start-time 옵션은 오디오 파이프라인 초기화 전에 적용되어
        # 시작 부분이 잘리는 문제가 있음. play() 후 Playing 상태가 되면
        # set_time()으로 정확하게 seek한다.
        deadline = time.monotonic() + 0.3
        while time.monotonic() < deadline:
            if self._player.get_state() == self._vlc.State.Playing:
                break
            time.sleep(0.005)
        if start > 0:
            self._player.set_time(int(start * 1000))

        self._play_start_time = time.monotonic()

        if end is not None:
            self._remaining = end - start
            self._stop_timer = threading.Timer(self._remaining, self._on_segment_end)
            self._stop_timer.daemon = True
            self._stop_timer.start()

    def _on_segment_end(self) -> None:
        self._player.stop()
        self._paused = False
        self._remaining = 0.0
        if self._on_complete:
            self._on_complete()

    def toggle_pause(self) -> None:
        import vlc
        if self._paused:
            # resume: restart a fresh play period from current paused position
            self._player.pause()  # vlc: pause() toggles pause→play
            self._paused = False
            self._play_start_time = time.monotonic()
            if self._remaining > 0:
                self._stop_timer = threading.Timer(self._remaining, self._on_segment_end)
                self._stop_timer.daemon = True
                self._stop_timer.start()
        elif self._player.get_state() == vlc.State.Playing:
            # pause: accumulate elapsed into _paused_offset, reduce remaining
            elapsed = time.monotonic() - self._play_start_time
            self._paused_offset += elapsed
            self._remaining = max(0.0, self._remaining - elapsed)
            if self._stop_timer:
                self._stop_timer.cancel()
                self._stop_timer = None
            self._player.pause()
            self._paused = True

    def is_playing(self) -> bool:
        import vlc
        return self._player.get_state() == vlc.State.Playing and not self._paused

    def get_position(self) -> float:
        if self._paused:
            return self._start_pos + self._paused_offset
        import vlc
        if self._player.get_state() != vlc.State.Playing:
            return self._start_pos + self._paused_offset
        return self._start_pos + self._paused_offset + (time.monotonic() - self._play_start_time)

    def stop(self) -> None:
        if self._stop_timer is not None:
            self._stop_timer.cancel()
            self._stop_timer = None
        self._paused = False
        self._player.stop()


def create_player(media_path: str) -> AudioPlayer:
    ext = Path(media_path).suffix.lower()
    if ext == ".mp4":
        return VLCAudioPlayer()
    return PygameAudioPlayer()
