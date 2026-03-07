import queue
import sys
import termios
import tty
from pathlib import Path

from .core.audio_player import AudioPlayer, create_player
from .core.file_finder import FileFinder
from .core.models import Session, Subtitle
from .core.progress_store import ProgressStore
from .core.stats_store import StatsStore
from .core.srt_parser import SRTParser
from .keyboard_handler import Action, KeyboardHandler
from .ui import RichUI


class AppController:
    def __init__(self) -> None:
        self.ui = RichUI()
        self.progress_store = ProgressStore()
        self.stats_store = StatsStore()
        self.file_finder = FileFinder()
        self.srt_parser = SRTParser()
        self.keyboard = KeyboardHandler()
        self.action_queue: queue.Queue[Action] = queue.Queue()

        self.player: AudioPlayer | None = None
        self.subtitles: list[Subtitle] = []
        self.current_index: int = 0
        self.media_path: str = ""
        self.srt_path: str = ""

    def run(self) -> None:
        self.ui.show_welcome()

        if not self._setup_session():
            return

        self._main_loop()

    # ------------------------------------------------------------------
    # Session setup
    # ------------------------------------------------------------------

    def _setup_session(self) -> bool:
        sessions = self.progress_store.load()
        if sessions:
            chosen = self.ui.show_progress_list(sessions)
            if chosen is not None:
                session = sessions[chosen]
                self.media_path = session.media_path
                self.srt_path = session.srt_path
                self.current_index = session.current_index
                self._load_subtitles()
                self._init_player()
                return True

        # new file selection
        return self._select_files(".")

    def _select_files(self, directory: str) -> bool:
        # select media file
        while True:
            media_files = self.file_finder.find_media(directory)
            if media_files:
                break
            if not Path(directory).exists():
                self.ui.show_message(f"[red]Path does not exist: {directory}[/red]")
            else:
                self.ui.show_message(
                    f"[yellow]No mp3/mp4 files found in: {directory}[/yellow]"
                )
            directory = self.ui.ask_path("Enter path to media files")
            if not directory:
                return False

        idx = self.ui.show_file_list(media_files, "Select a media file")
        self.media_path = media_files[idx]

        # select srt file
        srt_dir = directory
        while True:
            srt_files = self.file_finder.find_srt(srt_dir)
            if srt_files:
                break
            if not Path(srt_dir).exists():
                self.ui.show_message(f"[red]Path does not exist: {srt_dir}[/red]")
            else:
                self.ui.show_message(
                    f"[yellow]No srt files found in: {srt_dir}[/yellow]"
                )
            srt_dir = self.ui.ask_path("Enter path to srt files")
            if not srt_dir:
                return False

        idx = self.ui.show_file_list(srt_files, "Select a subtitle file")
        self.srt_path = srt_files[idx]

        self.current_index = 0
        self._load_subtitles()
        self._init_player()
        return True

    def _load_subtitles(self) -> None:
        self.subtitles = self.srt_parser.load(self.srt_path)

    def _init_player(self) -> None:
        self.player = create_player(self.media_path)

    # ------------------------------------------------------------------
    # Main loop
    # ------------------------------------------------------------------

    def _main_loop(self) -> None:
        self.keyboard.start(lambda action: self.action_queue.put(action))
        self._refresh_display()

        fd = sys.stdin.fileno()
        old_settings = termios.tcgetattr(fd)
        try:
            tty.setcbreak(fd)  # disable echo while keeping Ctrl+C working
            running = True
            while running:
                try:
                    action = self.action_queue.get(timeout=0.1)
                except queue.Empty:
                    continue

                if action == Action.QUIT:
                    self._handle_quit()
                    running = False
                elif action == Action.PLAY:
                    self._handle_play()
                elif action == Action.NEXT:
                    self._handle_next()
                elif action == Action.PREV:
                    self._handle_prev()
        finally:
            termios.tcflush(fd, termios.TCIFLUSH)
            termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)
            self.keyboard.stop()

    def _handle_play(self) -> None:
        self._play_current()

    def _handle_next(self) -> None:
        if self.current_index < len(self.subtitles) - 1:
            self.current_index += 1
        self._refresh_display()
        self._play_current()

    def _handle_prev(self) -> None:
        if self.current_index > 0:
            self.current_index -= 1
        self._refresh_display()
        self._play_current()

    def _handle_quit(self) -> None:
        if self.player:
            self.player.stop()
        self.progress_store.upsert(Session(
            media_path=self.media_path,
            srt_path=self.srt_path,
            current_index=self.current_index,
        ))
        self.ui.show_message("\n[dim]Progress saved. Exiting.[/dim]")

    def _play_current(self) -> None:
        if not self.subtitles or self.player is None:
            return
        sub = self.subtitles[self.current_index]
        self.player.play_segment(self.media_path, sub.start, sub.end)
        self.stats_store.increment_play(self.media_path, sub.index)

    def _refresh_display(self) -> None:
        self.ui.show_subtitles(self.subtitles, self.current_index)
