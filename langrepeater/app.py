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
from .keyboard_handler import Action, read_action
from .ui import RichUI


def _is_cjk_text(text: str) -> bool:
    """Return True if text contains CJK (Chinese/Japanese/Korean) characters."""
    return any(
        0x3000 <= ord(c) <= 0x9FFF or 0xF900 <= ord(c) <= 0xFAFF
        for c in text
    )


class AppController:
    def __init__(self) -> None:
        self.ui = RichUI()
        self.progress_store = ProgressStore()
        self.stats_store = StatsStore()
        self.file_finder = FileFinder()
        self.srt_parser = SRTParser()
        self.player: AudioPlayer | None = None
        self.subtitles: list[Subtitle] = []
        self.current_index: int = 0
        self.media_path: str = ""
        self.srt_path: str = ""
        self._paused: bool = False
        self._fd: int = -1
        self._old_settings: list = []

    def run(self) -> None:
        self.ui.show_welcome()
        while True:
            if not self._setup_session():
                return
            restart = self._main_loop()
            if not restart:
                return
            self.ui.show_welcome()

    # ------------------------------------------------------------------
    # Session setup
    # ------------------------------------------------------------------

    def _setup_session(self) -> bool:
        while True:
            sessions = self.progress_store.load()
            choice = self.ui.show_home_menu(has_sessions=bool(sessions))
            if choice == "quit":
                return False
            if choice == "resume":
                idx = self.ui.ask_resume_session(sessions)
                if idx is None:
                    continue
                session = sessions[idx]
                self.media_path = session.media_path
                self.srt_path = session.srt_path
                self.current_index = session.current_index
                self._load_subtitles()
                self._init_player()
                return True
            if choice == "url":
                if self._load_from_url():
                    return True
                continue
            if choice == "delete":
                self._handle_delete_session(sessions)
                continue
            # "new" = new local file
            if sessions:
                prev_dir = str(Path(sessions[0].media_path).parent)
                start_dir = self.ui.ask_folder(prev_dir)
                if start_dir is None:
                    continue
            else:
                start_dir = "."
            if self._select_files(start_dir):
                return True
            continue

    def _handle_delete_session(self, sessions: list) -> None:
        idx = self.ui.ask_delete_session(sessions)
        if idx is None:
            return
        if self.ui.confirm_delete(sessions[idx]):
            self.stats_store.delete(sessions[idx].media_path)
            self.progress_store.delete(idx)
            self.ui.show_message("[dim]Session deleted.[/dim]")

    def _load_from_url(self) -> bool:
        from .core import url_loader

        url = self.ui.ask_path("Enter URL (or C to cancel)")
        if not url or url.strip().lower() == "c":
            return False

        output_dir = str(Path.home() / "Downloads" / "LangRepeater")
        self.ui.show_message("[dim]Downloading...[/dim]")
        try:
            audio_path = url_loader.download(url, output_dir)
        except Exception as e:
            self.ui.show_message(f"[red]Download failed: {e}[/red]")
            return False

        self.ui.show_message("[dim]Transcribing with Whisper...[/dim]")
        try:
            srt_path = url_loader.transcribe(audio_path)
        except Exception as e:
            self.ui.show_message(f"[red]Transcription failed: {e}[/red]")
            return False

        self.media_path = audio_path
        self.srt_path = srt_path
        self.current_index = 0
        self._load_subtitles()
        self._init_player()
        return True

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
        if idx is None:
            return False
        self.media_path = media_files[idx]

        # select srt file: use same-name srt if exists, else transcribe
        srt_candidate = str(Path(self.media_path).with_suffix(".srt"))
        if Path(srt_candidate).exists():
            self.srt_path = srt_candidate
        else:
            self.ui.show_message("[dim]No matching srt file found. Transcribing with Whisper...[/dim]")
            from .core import url_loader
            try:
                self.srt_path = url_loader.transcribe(self.media_path)
            except Exception as e:
                self.ui.show_message(f"[red]Transcription failed: {e}[/red]")
                return False

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

    def _main_loop(self) -> bool:  # True = HOME (restart), False = QUIT
        self._refresh_display()

        fd = sys.stdin.fileno()
        old_settings = termios.tcgetattr(fd)
        self._fd = fd
        self._old_settings = old_settings
        try:
            tty.setcbreak(fd)  # disable echo while keeping Ctrl+C working
            running = True
            restart = False
            while running:
                action = read_action(fd, timeout=0.1)
                if action is None:
                    continue

                if action == Action.QUIT:
                    self._handle_quit()
                    running = False
                elif action == Action.HOME:
                    self._handle_home()
                    restart = True
                    running = False
                elif action == Action.PLAY:
                    self._handle_play()
                elif action == Action.RESTART:
                    self._handle_restart()
                elif action == Action.NEXT:
                    self._handle_next()
                elif action == Action.PREV:
                    self._handle_prev()
                elif action == Action.SHIFT_START_EARLIER:
                    self._handle_shift_start(-0.1)
                elif action == Action.SHIFT_START_LATER:
                    self._handle_shift_start(0.1)
                elif action == Action.SHIFT_END_EARLIER:
                    self._handle_shift_end(-0.1)
                elif action == Action.SHIFT_END_LATER:
                    self._handle_shift_end(0.1)
                elif action == Action.HELP:
                    self.ui.show_help()
                elif action == Action.MERGE:
                    self._handle_merge()
                elif action == Action.SPLIT:
                    self._handle_split()
                elif action == Action.PRINT_STATS:
                    self._handle_print_stats()
        finally:
            termios.tcflush(fd, termios.TCIFLUSH)
            termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)
        return restart

    def _handle_play(self) -> None:
        # Space: toggle play/pause; if stopped, start playing
        if self.player is None:
            return
        if self.player.is_playing():
            self.player.toggle_pause()
            self._paused = True
        elif self._paused:
            self.player.toggle_pause()
            self._paused = False
        else:
            self._play_current()

    def _handle_restart(self) -> None:
        # S: always restart segment from beginning
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

    def _handle_home(self) -> None:
        if self.player:
            self.player.stop()
        self.progress_store.upsert(Session(
            media_path=self.media_path,
            srt_path=self.srt_path,
            current_index=self.current_index,
        ))

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
        self._paused = False
        sub = self.subtitles[self.current_index]
        media_path = self.media_path
        sub_index = sub.index
        self.player.play_segment(
            self.media_path, sub.start, sub.end,
            on_complete=lambda: self.stats_store.increment_play(media_path, sub_index),
        )

    def _handle_shift_start(self, delta: float) -> None:
        if not self.subtitles:
            return
        sub = self.subtitles[self.current_index]
        new_start = max(0.0, sub.start + delta)
        if new_start >= sub.end:
            return
        sub.start = round(new_start, 1)
        self.srt_parser.save(self.srt_path, self.subtitles)
        self._refresh_display()
        self._play_current()

    def _handle_shift_end(self, delta: float) -> None:
        if not self.subtitles:
            return
        sub = self.subtitles[self.current_index]
        new_end = sub.end + delta
        if new_end <= sub.start:
            return
        sub.end = round(new_end, 1)
        self.srt_parser.save(self.srt_path, self.subtitles)
        self._refresh_display()
        self._play_current()

    def _handle_merge(self) -> None:
        if not self.subtitles:
            return
        if self.current_index >= len(self.subtitles) - 1:
            return  # no next segment
        cur = self.subtitles[self.current_index]
        nxt = self.subtitles[self.current_index + 1]
        cur_index = cur.index
        nxt_index = nxt.index
        cur.end = nxt.end
        sep = "" if _is_cjk_text(cur.text.rstrip() or nxt.text.lstrip()) else " "
        cur.text = cur.text.rstrip() + sep + nxt.text.lstrip()
        self.subtitles.pop(self.current_index + 1)
        self._reindex_subtitles()
        self.stats_store.on_merge(self.media_path, cur_index, nxt_index, len(self.subtitles))
        self.srt_parser.save(self.srt_path, self.subtitles)
        self._refresh_display()
        self._play_current()

    def _handle_split(self) -> None:
        if not self.subtitles:
            return
        sub = self.subtitles[self.current_index]
        sub_index = sub.index
        # temporarily restore terminal for interactive input
        termios.tcsetattr(self._fd, termios.TCSADRAIN, self._old_settings)
        try:
            split_pos = self.ui.ask_split_point(sub)
        finally:
            tty.setcbreak(self._fd)
        if split_pos is None:
            return
        text_a = sub.text[:split_pos].rstrip()
        text_b = sub.text[split_pos:].lstrip()
        words_a = len(text_a.split())
        words_total = len(sub.text.split())
        if words_total > 1:
            ratio = words_a / words_total
        else:
            ratio = len(text_a) / len(sub.text) if sub.text else 0.5
        split_time = round(sub.start + (sub.end - sub.start) * ratio, 3)
        from .core.models import Subtitle
        sub_a = Subtitle(index=0, start=sub.start, end=split_time, text=text_a)
        sub_b = Subtitle(index=0, start=split_time, end=sub.end, text=text_b)
        self.subtitles[self.current_index:self.current_index + 1] = [sub_a, sub_b]
        self._reindex_subtitles()
        self.stats_store.on_split(self.media_path, sub_index, len(self.subtitles))
        self.srt_parser.save(self.srt_path, self.subtitles)
        self._refresh_display()
        self._play_current()

    def _reindex_subtitles(self) -> None:
        for i, sub in enumerate(self.subtitles):
            sub.index = i + 1

    def _handle_print_stats(self) -> None:
        if not self.subtitles:
            return
        stats = self.stats_store.load(self.media_path)
        # build index → subtitle map
        sub_map = {sub.index: sub for sub in self.subtitles}
        # TOP10 by play count
        top10 = sorted(
            stats.subtitle_play_counts.items(),
            key=lambda x: x[1],
            reverse=True,
        )[:10]
        # total study time = sum of duration × play count
        total_seconds = sum(
            (sub_map[idx].end - sub_map[idx].start) * count
            for idx, count in stats.subtitle_play_counts.items()
            if idx in sub_map
        )
        self.ui.show_learning_stats(top10, sub_map, total_seconds)

    def _refresh_display(self) -> None:
        self.ui.show_subtitles(self.subtitles, self.current_index)
