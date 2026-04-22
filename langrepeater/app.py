import os
import select
import sys
import termios
import time
import tty
from pathlib import Path

from .core.audio_player import AudioPlayer, PygameAudioPlayer, create_player
from .core.bookmark_store import BookmarkStore
from .core.file_finder import FileFinder
from .core.models import Session, Subtitle, _index_key, _merged_index, _split_indices
from .core.progress_store import ProgressStore
from .core.settings_store import SettingsStore
from .core.stats_store import StatsStore
from .core.srt_parser import SRTParser, _words_json_path, _words_yaml_path
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
        self.settings_store = SettingsStore()
        self.settings_store.load()
        self.stats_store = StatsStore()
        self.bookmark_store = BookmarkStore()
        self.file_finder = FileFinder()
        self.srt_parser = SRTParser()
        self.player: AudioPlayer | None = None
        self.subtitles: list[Subtitle] = []
        self.all_word_timestamps: list = []  # flat WordTimestamp list from YAML
        self.current_index: int = 0
        self.media_path: str = ""
        self.srt_path: str = ""
        self._paused: bool = False
        self._subtitle_masked: bool = True
        self._fd: int = -1
        self._old_settings: list = []
        self._stats_ranked: list[tuple[int, int]] = []
        self._stats_sub_map: dict[int, object] = {}
        self._stats_total_seconds: float = 0.0
        self._stats_page: int = 0
        self._showing_stats: bool = False
        self._showing_date_stats: bool = False
        self._date_stats_entries: list[tuple[str, dict[int, int]]] = []
        self._date_stats_page: int = 0
        self._date_stats_cursor: int = 0
        self._play_start_time: float = 0.0
        self._play_duration: float = 0.0
        self._paused_at: float = 0.0
        self._paused_progress: float = 0.0
        self._was_playing: bool = False
        self._mode: str = "LR"  # "L" = Listening mode, "LR" = Listen & Repeat mode, "R" = Review mode
        self._lr_mode_index: int = 0  # LR모드 복귀 시 돌아갈 자막 인덱스
        self._review_list: list[int] = []  # R모드: 샘플링된 자막 0-based 인덱스 목록
        self._review_index: int = 0  # R모드: review_list 내 현재 위치 (0-9)
        self._review_lr_return_index: int = 0  # R모드 → LR모드 복귀 시 돌아갈 인덱스
        self._back_index: int = -1  # BACK 키 복귀용 이전 자막 인덱스 (-1 = 없음)
        self._back_review_index: int = 0  # R모드 BACK 키 복귀용 이전 review_index
        self._bookmarks: set[str] = set()  # 현재 미디어의 북마크된 자막 인덱스
        self._wrong_transcriptions: set[str] = set()  # 틀린 받아쓰기 자막 인덱스
        self._showing_bookmarks: bool = False
        self._bookmark_page: int = 0
        self._bookmark_cursor: int = 0  # 북마크 목록 내 절대 커서 위치
        self._stats_cursor: int = 0  # 통계 화면 내 절대 커서 위치
        self._sentence_play_origin: int = -1  # S키 문장 전체 재생 중 복귀할 원래 인덱스 (-1 = 비활성)

    def run(self) -> None:
        while True:
            if not self._setup_session():
                return
            restart = self._main_loop()
            if not restart:
                return

    # ------------------------------------------------------------------
    # Session setup
    # ------------------------------------------------------------------

    def _setup_session(self) -> bool:
        while True:
            self.ui.show_welcome()
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
                self.current_index = session.current_index
                if Path(session.srt_path).exists():
                    self.srt_path = session.srt_path
                else:
                    srt_candidate = str(Path(session.media_path).with_suffix(".srt"))
                    if Path(srt_candidate).exists() or _words_json_path(srt_candidate).exists() or _words_yaml_path(srt_candidate).exists():
                        self.srt_path = srt_candidate
                    else:
                        self.ui.show_message("[dim]SRT file not found. Transcribing with whisper-cli...[/dim]")
                        from .core import url_loader
                        try:
                            self.srt_path = url_loader.transcribe(session.media_path)
                        except Exception as e:
                            self.ui.show_message(f"[red]Transcription failed: {e}[/red]")
                            continue
                self._load_subtitles()
                self._init_player()
                return True
            if choice == "url" or choice.startswith("url:"):
                url = choice[4:] if choice.startswith("url:") else None
                if self._load_from_url(url=url):
                    return True
                continue
            if choice == "delete":
                self._handle_delete_session(sessions)
                continue
            # "new" = new local file
            if sessions:
                prev_dir = str(Path(sessions[0].media_path).parent)
                result = self.ui.ask_folder(prev_dir)
                if result is None:
                    continue
                if Path(result).is_file():
                    if self._select_file_directly(result):
                        return True
                    continue
                start_dir = result
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

    def _load_from_url(self, url: str | None = None) -> bool:
        from .core import url_loader

        if url is None:
            url = self.ui.ask_path("Enter URL")
        if not url:
            return False

        output_dir = str(Path.home() / "Downloads" / "LangRepeater")
        self.ui.show_message("[dim]Downloading...[/dim]")
        try:
            audio_path = url_loader.download(url, output_dir)
        except Exception as e:
            import re as _re
            msg = _re.sub(r'\x1b\[[0-9;]*m', '', str(e)).strip()
            self.ui.show_message(f"[red]Download failed:[/red] {msg}")
            self.ui.show_message("[dim]Press Enter to continue...[/dim]")
            self.ui.wait_for_enter()
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

    def _select_file_directly(self, file_path: str) -> bool:
        """Handle a media file selected directly via file dialog."""
        from .core import url_loader

        path = Path(file_path)
        if path.suffix.lower() == ".mp4":
            self.ui.show_message("[dim]Extracting audio from mp4...[/dim]")
            try:
                media_path = url_loader.extract_audio(file_path)
            except Exception as e:
                self.ui.show_message(f"[red]Audio extraction failed: {e}[/red]")
                return False
        else:
            media_path = file_path

        self.media_path = media_path
        srt_candidate = str(Path(media_path).with_suffix(".srt"))
        if Path(srt_candidate).exists() or _words_json_path(srt_candidate).exists() or _words_yaml_path(srt_candidate).exists():
            self.srt_path = srt_candidate
        else:
            self.ui.show_message("[dim]No matching srt file found. Transcribing with whisper-cli...[/dim]")
            try:
                self.srt_path = url_loader.transcribe(media_path)
            except Exception as e:
                self.ui.show_message(f"[red]Transcription failed: {e}[/red]")
                return False

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

        # select srt file: use same-name srt (or words json/yaml) if exists, else transcribe
        srt_candidate = str(Path(self.media_path).with_suffix(".srt"))
        if Path(srt_candidate).exists() or _words_json_path(srt_candidate).exists() or _words_yaml_path(srt_candidate).exists():
            self.srt_path = srt_candidate
        else:
            self.ui.show_message("[dim]No matching srt file found. Transcribing with whisper-cli...[/dim]")
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
        self.all_word_timestamps = self.srt_parser.load_words_json(self.srt_path) or self.srt_parser.load_words_yaml(self.srt_path)
        self._bookmarks = self.bookmark_store.load(self.media_path)
        self._wrong_transcriptions = self.bookmark_store.load_wrong(self.media_path)
        # total_segments를 즉시 저장하여 세션 목록에 반영
        self.progress_store.upsert(Session(
            media_path=self.media_path,
            srt_path=self.srt_path,
            current_index=self.current_index,
            total_segments=len(self.subtitles),
        ))

    def _init_player(self) -> None:
        self.player = create_player(self.media_path)
        if isinstance(self.player, PygameAudioPlayer):
            self.player._de_esser_reduction_db = self.settings_store.de_esser_reduction_db

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
            sys.stdout.write("\033[?25l")
            sys.stdout.flush()
            running = True
            restart = False
            while running:
                action = read_action(fd, timeout=0.1)
                if action is None:
                    if not self._showing_stats and not self._showing_date_stats and not self._showing_bookmarks:
                        is_playing = self.player is not None and self.player.is_playing()
                        if self._sentence_play_origin >= 0 and self.subtitles:
                            if is_playing:
                                pos = self.player.get_position()
                                new_index = self._find_subtitle_index_by_pos(pos)
                                if new_index != self.current_index:
                                    self.current_index = new_index
                                    self._refresh_display()
                                sub = self.subtitles[self.current_index]
                                duration = sub.end - sub.start
                                if duration > 0:
                                    progress = min(1.0, max(0.0, (pos - sub.start) / duration))
                                    self.ui.update_animation_line(progress)
                            elif self._was_playing and not self._paused:
                                self.current_index = self._sentence_play_origin
                                self._sentence_play_origin = -1
                                self._refresh_display()
                                self.ui.update_animation_line(1.0, dim=True)
                            self._was_playing = is_playing
                            continue
                        if self._mode == "L" and self.subtitles:
                            if is_playing:
                                pos = self.player.get_position()
                                new_index = self._find_subtitle_index_by_pos(pos)
                                if new_index != self.current_index:
                                    self.current_index = new_index
                                    self._refresh_display()
                                sub = self.subtitles[self.current_index]
                                duration = sub.end - sub.start
                                if duration > 0:
                                    progress = min(1.0, max(0.0, (pos - sub.start) / duration))
                                    self.ui.update_animation_line(progress)
                            elif self._was_playing and not self._paused:
                                self.ui.update_animation_line(1.0, dim=True)
                        elif self._play_duration > 0:
                            if is_playing:
                                elapsed = time.monotonic() - self._play_start_time
                                progress = min(1.0, elapsed / self._play_duration)
                                self.ui.update_animation_line(progress)
                            elif self._was_playing and not self._paused:
                                self.ui.update_animation_line(1.0, dim=True)
                        self._was_playing = is_playing
                    continue

                if self._showing_bookmarks:
                    if action == Action.QUIT:
                        self._handle_quit()
                        running = False
                    elif action in (Action.NEXT, Action.PREV):
                        self._handle_bookmark_cursor(1 if action == Action.NEXT else -1)
                    elif action == Action.STATS_NEXT:
                        self._handle_bookmark_page(1)
                    elif action == Action.STATS_PREV:
                        self._handle_bookmark_page(-1)
                    elif action == Action.BOOKMARK_SELECT:
                        self._handle_bookmark_select()
                    else:
                        self._showing_bookmarks = False
                        self._refresh_display()
                    continue

                if self._showing_stats or self._showing_date_stats:
                    if action == Action.QUIT:
                        self._handle_quit()
                        running = False
                    elif action in (Action.STATS_NEXT, Action.STATS_PREV):
                        self._handle_stats_page(1 if action == Action.STATS_NEXT else -1)
                    elif action in (Action.NEXT, Action.PREV) and self._showing_stats:
                        self._handle_stats_cursor(1 if action == Action.NEXT else -1)
                    elif action in (Action.NEXT, Action.PREV) and self._showing_date_stats:
                        self._handle_date_stats_cursor(1 if action == Action.NEXT else -1)
                    elif action == Action.BOOKMARK_SELECT and self._showing_stats:
                        self._handle_stats_select()
                    elif action == Action.PRINT_STATS and self._showing_stats:
                        self._showing_stats = False
                        self._refresh_display()
                    elif action == Action.PRINT_DATE_STATS and self._showing_date_stats:
                        self._showing_date_stats = False
                        self._refresh_display()
                    else:
                        self._showing_stats = False
                        self._showing_date_stats = False
                        self._refresh_display()
                    continue

                if action == Action.QUIT:
                    self._handle_quit()
                    running = False
                elif action == Action.HOME:
                    self._handle_home()
                    restart = True
                    running = False
                elif action == Action.MODE_LISTENING:
                    if self._mode != "L":
                        if self._mode == "R":
                            self.current_index = self._review_lr_return_index
                        self._lr_mode_index = self.current_index
                        self._mode = "L"
                        if self.player:
                            self.player.stop()
                        self._paused = False
                        self._was_playing = False
                        self._play_duration = 0.0
                        self._refresh_display()
                elif action == Action.MODE_LISTEN_REPEAT:
                    if self._mode != "LR":
                        prev_mode = self._mode
                        self._mode = "LR"
                        if self.player:
                            self.player.stop()
                        self._paused = False
                        self._was_playing = False
                        self._play_duration = 0.0
                        if prev_mode == "L":
                            self.current_index = self._lr_mode_index
                        elif prev_mode == "R":
                            self.current_index = self._review_lr_return_index
                        self._refresh_display()
                elif action == Action.MODE_REVIEW:
                    if self._mode != "R":
                        self._review_lr_return_index = self.current_index
                        if self.player:
                            self.player.stop()
                        self._paused = False
                        self._was_playing = False
                        self._play_duration = 0.0
                        self._mode = "R"
                        if self._review_list:
                            # 이전 샘플링 상태가 있으면 복원
                            self.current_index = self._review_list[self._review_index]
                            self._refresh_display()
                        else:
                            # 샘플링이 없으면 자동 resample
                            self._refresh_display()
                            self._handle_review()
                elif action == Action.BACK:
                    self._handle_back()
                elif self._mode == "R" and action == Action.REVIEW:
                    self._handle_review()
                elif self._mode == "LR" and action == Action.REVIEW:
                    self._handle_resync_timestamp()
                elif self._mode == "R" and action == Action.NEXT:
                    self._handle_review_next()
                elif self._mode == "R" and action == Action.PREV:
                    self._handle_review_prev()
                elif self._mode == "R" and action == Action.STATS_NEXT:
                    self._handle_review_page(1)
                elif self._mode == "R" and action == Action.STATS_PREV:
                    self._handle_review_page(-1)
                elif action == Action.PLAY:
                    self._handle_play()
                elif action == Action.NEXT:
                    self._handle_next()
                elif action == Action.PREV:
                    self._handle_prev()
                elif action == Action.TOGGLE_SUBTITLE:
                    self._subtitle_masked = not self._subtitle_masked
                    self._refresh_display()
                elif action == Action.STATS_NEXT and self._mode == "L":
                    self._handle_l_page(1)
                elif action == Action.STATS_PREV and self._mode == "L":
                    self._handle_l_page(-1)
                elif action == Action.GOTO and self._mode == "L":
                    self._handle_goto()
                elif action == Action.RESTART and self._mode == "L":
                    self._handle_restart()
                elif self._mode == "L":
                    pass  # L모드에서는 위 키 외 다른 키 무시
                elif action == Action.GOTO and self._mode != "R":
                    self._handle_goto()
                elif action == Action.MERGE:
                    if self._mode != "R":
                        self._handle_merge()
                elif action == Action.SPLIT:
                    if self._mode != "R":
                        self._handle_split()
                elif action == Action.TRANSCRIBE:
                    self._handle_transcribe()
                elif action == Action.RESYNC_START:
                    self._handle_resync_timestamp(resync_end=False)
                elif action == Action.RESYNC_END:
                    self._handle_resync_timestamp(resync_start=False)
                elif action == Action.SIBILANT_DOWN:
                    self._handle_sibilant(+1.0)
                elif action == Action.SIBILANT_UP:
                    self._handle_sibilant(-1.0)
                elif action == Action.RESTART:
                    self._handle_restart()
                elif action == Action.SHIFT_START_EARLIER:
                    self._handle_shift_start(-0.1)
                elif action == Action.SHIFT_START_LATER:
                    self._handle_shift_start(0.1)
                elif action == Action.SHIFT_END_EARLIER:
                    self._handle_shift_end(-0.1)
                elif action == Action.SHIFT_END_LATER:
                    self._handle_shift_end(0.1)
                elif action == Action.BOOKMARK:
                    self._handle_bookmark_toggle()
                elif action == Action.BOOKMARK_LIST:
                    if self._mode != "R":
                        self._handle_bookmark_list()
                elif action == Action.PRINT_STATS:
                    self._handle_print_stats()
                    self._showing_stats = True
                elif action == Action.PRINT_DATE_STATS:
                    self._handle_print_date_stats()
                    self._showing_date_stats = True
                elif action == Action.STATS_NEXT:
                    self._handle_l_page(1)
                elif action == Action.STATS_PREV:
                    self._handle_l_page(-1)
        finally:
            sys.stdout.write("\033[?25h")
            sys.stdout.flush()
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
            self._paused_at = time.monotonic()
            if self._play_duration > 0:
                elapsed = self._paused_at - self._play_start_time
                self._paused_progress = min(1.0, elapsed / self._play_duration)
                self.ui.update_animation_line(self._paused_progress, dim=True)
        elif self._paused:
            self.player.toggle_pause()
            self._paused = False
            self._play_start_time += time.monotonic() - self._paused_at
        else:
            self._refresh_display()
            if self._mode == "L":
                self._start_l_mode_playback()
            else:
                self._play_current()

    def _handle_restart(self) -> None:
        self._refresh_display()
        if self._mode == "L":
            self._start_l_mode_playback()
            return
        siblings = self._get_split_siblings(self.current_index)
        if len(siblings) > 1:
            self._play_sentence_range(siblings)
        else:
            self._play_current()

    def _get_split_siblings(self, pos: int) -> list[int]:
        """index 구조 기반으로 동일 원본에서 분리된 형제 자막의 0-based 위치 목록 반환."""
        sub_index = self.subtitles[pos].index
        parts = sub_index.split('-')
        if len(parts) < 2:
            return [pos]
        parent_prefix = '-'.join(parts[:-1]) + '-'
        depth = len(parts)
        result = [
            i for i, sub in enumerate(self.subtitles)
            if sub.index.startswith(parent_prefix) and len(sub.index.split('-')) == depth
        ]
        return result if len(result) > 1 else [pos]

    def _play_sentence_range(self, siblings: list[int]) -> None:
        """분리된 문장 전체(첫 형제 시작 ~ 마지막 형제 끝)를 재생. 완료 후 current_index 복귀."""
        if self.player is None:
            return
        self._sentence_play_origin = self.current_index
        self._paused = False
        self.current_index = siblings[0]
        self._refresh_display()
        start = self.subtitles[siblings[0]].start
        end = self.subtitles[siblings[-1]].end
        self._play_start_time = time.monotonic()
        self._play_duration = end - start
        self._was_playing = False
        self.ui.update_animation_line(0.0)
        self.player.play_segment(self.media_path, start, end, on_complete=None)

    def _handle_next(self) -> None:
        self._save_back()
        if self.current_index < len(self.subtitles) - 1:
            self.current_index += 1
        self._refresh_display()
        if self._mode == "L":
            self._start_l_mode_playback()
        else:
            self._play_current()

    def _handle_prev(self) -> None:
        self._save_back()
        if self.current_index > 0:
            self.current_index -= 1
        self._refresh_display()
        if self._mode == "L":
            self._start_l_mode_playback()
        else:
            self._play_current()

    def _save_progress(self) -> None:
        save_index = self._lr_mode_index if self._mode == "L" else self.current_index
        self.progress_store.upsert(Session(
            media_path=self.media_path,
            srt_path=self.srt_path,
            current_index=save_index,
            total_segments=len(self.subtitles),
        ))
        if self.subtitles:
            self.stats_store.update_progress(
                self.media_path, save_index, len(self.subtitles)
            )

    _SENTENCE_END_PUNCT = frozenset('.!?。！？')

    def _expand_to_siblings(self, idx: int) -> list[int]:
        """분리된 문장 감지: 구두점/대소문자 기반으로 앞뒤 문장 포함.

        - 문장이 .!?로 끝나지 않으면 → 바로 뒤 문장 추가
        - 문장이 대문자로 시작하지 않으면 → 바로 앞 문장 추가
        """
        n = len(self.subtitles)
        group = [idx]
        text = self.subtitles[idx].text.strip()
        if text and text[-1] not in self._SENTENCE_END_PUNCT:
            if idx + 1 < n:
                group.append(idx + 1)
        if text and not text[0].isupper():
            if idx - 1 >= 0:
                group.insert(0, idx - 1)
        return group

    def _sample_review_list(self) -> list[int] | None:
        """학습통계 기반 확률분포로 총 문장 수가 10이 되도록 그룹 단위 샘플링.

        분리된 문장은 구두점/대소문자 휴리스틱으로 감지하여 같은 그룹으로 묶인다.
        그룹을 가중치 비복원 추출로 하나씩 선택하고, 누적 문장 수가 10 이상이면 종료.
        반환값은 0-based 인덱스 flat 리스트 (그룹 내 순서 유지).
        """
        import random
        stats = self.stats_store.load(self.media_path)
        idx_to_pos = {sub.index: i for i, sub in enumerate(self.subtitles)}
        valid: dict[int, int] = {}
        for idx, count in stats.subtitle_play_counts.items():
            pos = idx_to_pos.get(idx)
            if pos is not None and count > 0:
                valid[pos] = count
        if len(valid) < 10:
            return None

        # 중복 없는 그룹 풀 구성 (멤버 기반 merge: rep 기반 skip → 겹치면 병합)
        member_to_pool_idx: dict[int, int] = {}
        pool: list[list[int]] = []   # 각 원소는 0-based 인덱스 그룹
        pool_weights: list[float] = []
        for idx in sorted(valid.keys()):
            group = self._expand_to_siblings(idx)
            # 기존 풀 항목과 겹치는 멤버가 있으면 해당 항목에 병합
            target_pi: int | None = None
            for member in group:
                if member in member_to_pool_idx:
                    target_pi = member_to_pool_idx[member]
                    break
            if target_pi is not None:
                existing = set(pool[target_pi])
                for member in group:
                    if member not in existing:
                        pool[target_pi].append(member)
                        existing.add(member)
                        member_to_pool_idx[member] = target_pi
                pool[target_pi].sort()
                pool_weights[target_pi] = float(sum(valid.get(i, 0) for i in pool[target_pi]))
            else:
                weight = float(sum(valid.get(i, 0) for i in group))
                if weight > 0:
                    pi = len(pool)
                    pool.append(list(group))
                    pool_weights.append(weight)
                    for member in group:
                        member_to_pool_idx[member] = pi

        if len(pool) < 10:
            return None

        # 비복원 가중치 추출: 총 문장 수가 10 이상이 될 때까지
        remaining = list(range(len(pool)))
        weights = list(pool_weights)
        result: list[int] = []
        sentence_count = 0

        while sentence_count < 10 and remaining:
            total_w = sum(weights[i] for i in remaining)
            r = random.uniform(0, total_w)
            cumsum = 0.0
            chosen_pos = len(remaining) - 1
            for pos, i in enumerate(remaining):
                cumsum += weights[i]
                if r <= cumsum:
                    chosen_pos = pos
                    break
            chosen_i = remaining.pop(chosen_pos)
            group = pool[chosen_i]
            result.extend(group)
            sentence_count += len(group)

        return result

    def _handle_review(self) -> None:
        """R 키: 10개 문장 샘플링 (또는 재샘플링)."""
        if not self.subtitles:
            return
        sampled = self._sample_review_list()
        if sampled is None:
            self._refresh_display()
            self.ui.show_message("[yellow]Need at least 10 studied segments to start review.[/yellow]")
            return
        self._review_list = sampled
        self._review_index = 0
        self.current_index = self._review_list[0]
        self._refresh_display()
        self._play_current()

    def _handle_review_next(self) -> None:
        if not self._review_list:
            self._handle_next()
            return
        self._save_back()
        if self._review_index < len(self._review_list) - 1:
            self._review_index += 1
            self.current_index = self._review_list[self._review_index]
        self._refresh_display()
        self._play_current()

    def _handle_review_prev(self) -> None:
        if not self._review_list:
            self._handle_prev()
            return
        self._save_back()
        if self._review_index > 0:
            self._review_index -= 1
            self.current_index = self._review_list[self._review_index]
        self._refresh_display()
        self._play_current()

    def _handle_review_page(self, direction: int) -> None:
        if not self._review_list:
            self._handle_l_page(direction)
            return
        new_idx = max(0, min(len(self._review_list) - 1, self._review_index + direction * 3))
        if new_idx != self._review_index:
            self._save_back()
            self._review_index = new_idx
            self.current_index = self._review_list[self._review_index]
        self._refresh_display()
        self._play_current()

    def _save_back(self) -> None:
        self._back_index = self.current_index
        self._back_review_index = self._review_index

    def _handle_back(self) -> None:
        if self._back_index < 0:
            return
        self.current_index, self._back_index = self._back_index, self.current_index
        self._review_index, self._back_review_index = self._back_review_index, self._review_index
        self._refresh_display()
        if self._mode == "L":
            self._start_l_mode_playback()
        else:
            self._play_current()

    def _handle_home(self) -> None:
        if self.player:
            self.player.stop()
        self._save_progress()

    def _handle_quit(self) -> None:
        if self.player:
            self.player.stop()
        self._save_progress()
        self.ui.show_message("\n[dim]Progress saved. Exiting.[/dim]")

    def _handle_l_page(self, direction: int) -> None:
        """화면에 표시된 3문장 단위로 이동 (L/LR 공용)."""
        if not self.subtitles:
            return
        new_index = max(0, min(len(self.subtitles) - 1, self.current_index + direction * 3))
        if new_index != self.current_index:
            self._save_back()
            self.current_index = new_index
            self._refresh_display()
            if self._mode == "L":
                self._start_l_mode_playback()
            else:
                self._play_current()

    def _start_l_mode_playback(self) -> None:
        """L모드: 현재 자막 시작점부터 종료 타이머 없이 연속 재생."""
        if not self.subtitles or self.player is None:
            return
        self._paused = False
        sub = self.subtitles[self.current_index]
        self._was_playing = False
        self.player.play_segment(self.media_path, sub.start, end=None, on_complete=None)

    def _find_subtitle_index_by_pos(self, pos: float) -> int:
        """재생 위치(초)에 해당하는 자막 인덱스 반환."""
        for i, sub in enumerate(self.subtitles):
            if sub.start <= pos < sub.end:
                return i
        return self.current_index

    def _play_current(self) -> None:
        if not self.subtitles or self.player is None:
            return
        self._paused = False
        sub = self.subtitles[self.current_index]
        media_path = self.media_path
        sub_index = sub.index
        self._play_start_time = time.monotonic()
        self._play_duration = sub.end - sub.start
        self._was_playing = False
        self.ui.update_animation_line(0.0)
        self.player.play_segment(
            self.media_path, sub.start, sub.end,
            on_complete=lambda: self.stats_store.increment_play(media_path, sub_index),
        )

    def _play_preview(self, start: float, end: float) -> None:
        if self.player is None:
            return
        self._paused = False
        self._play_duration = end - start
        self._play_start_time = time.monotonic()
        self._was_playing = False
        self.player.play_segment(self.media_path, start, end, on_complete=None)

    def _handle_shift_start(self, delta: float) -> None:
        if not self.subtitles:
            return
        sub = self.subtitles[self.current_index]
        new_start = max(0.0, sub.start + delta)
        if new_start >= sub.end:
            return
        sub.start = round(new_start, 2)
        self.srt_parser.save(self.srt_path, self.subtitles)
        self._refresh_display()
        preview_end = min(sub.end, sub.start + 1.0)
        self._play_preview(sub.start, preview_end)

    def _handle_shift_end(self, delta: float) -> None:
        if not self.subtitles:
            return
        sub = self.subtitles[self.current_index]
        new_end = sub.end + delta
        if new_end <= sub.start:
            return
        sub.end = round(new_end, 2)
        self.srt_parser.save(self.srt_path, self.subtitles)
        self._refresh_display()
        preview_start = max(sub.start, sub.end - 1.0)
        self._play_preview(preview_start, sub.end)

    def _handle_merge(self) -> None:
        if not self.subtitles:
            return
        if self.current_index >= len(self.subtitles) - 1:
            return  # no next segment
        cur = self.subtitles[self.current_index]
        nxt = self.subtitles[self.current_index + 1]
        cur_idx = cur.index
        nxt_idx = nxt.index
        result_idx = _merged_index(cur_idx, nxt_idx)
        cur.index = result_idx
        cur.end = nxt.end
        sep = "" if _is_cjk_text(cur.text.rstrip() or nxt.text.lstrip()) else " "
        cur.text = cur.text.rstrip() + sep + nxt.text.lstrip()
        self.subtitles.pop(self.current_index + 1)
        self.stats_store.on_merge(self.media_path, cur_idx, nxt_idx, result_idx)
        # 머지 후 뒤 항목 순번을 result_idx 다음부터 순차 재지정
        remap = self._reindex_after(self.current_index + 1, _index_key(result_idx)[0] + 1)
        # 북마크: 흡수된 nxt 항목 → result로 이동
        bm_remap = dict(remap)
        if nxt_idx != result_idx:
            bm_remap[nxt_idx] = result_idx
        self.stats_store.remap_indices(self.media_path, remap)
        self.bookmark_store.remap_indices(self.media_path, bm_remap)
        self._bookmarks = self.bookmark_store.load(self.media_path)
        self._wrong_transcriptions = self.bookmark_store.load_wrong(self.media_path)
        self.srt_parser.save(self.srt_path, self.subtitles)
        self._refresh_display()
        self._play_current()

    def _handle_goto(self) -> None:
        if not self.subtitles:
            return
        termios.tcsetattr(self._fd, termios.TCSADRAIN, self._old_settings)
        try:
            raw = self.ui.ask_goto_number(len(self.subtitles))
        finally:
            tty.setcbreak(self._fd)
        if raw is None:
            self._refresh_display()
            return
        self._save_back()
        self.current_index = raw - 1
        self._refresh_display()
        if self._mode == "L":
            self._start_l_mode_playback()
        else:
            self._play_current()

    def _handle_split(self) -> None:
        if not self.subtitles:
            return
        sub = self.subtitles[self.current_index]
        orig_idx = sub.index
        split_pos = self.ui.ask_split_point(sub, self._fd)
        if split_pos is None:
            self._refresh_display()
            return
        text_a = sub.text[:split_pos].rstrip()
        text_b = sub.text[split_pos:].lstrip()
        split_time = round(self._split_time_from_word_timestamps(sub, split_pos), 3)
        parts = orig_idx.split('-')
        base_int = _index_key(orig_idx)[0]
        sentence_end = bool(text_a) and text_a[-1] in self._SENTENCE_END_PUNCT
        if sentence_end:
            # 문장 종료: 첫 번째 인덱스 유지, 두 번째 = 다음 정수, 후속 +1 shift
            idx_a = orig_idx
            idx_b = str(base_int + 1)
            reindex_start_num = base_int + 2
        elif len(parts) >= 2:
            # 문장 중간 + suffix 인덱스: 끝 번호 증가, shift 없음
            idx_a = orig_idx
            idx_b = '-'.join(parts[:-1]) + '-' + str(int(parts[-1]) + 1)
            reindex_start_num = base_int + 1
        else:
            # 문장 중간 + plain integer: 기존 -1/-2 동작
            idx_a, idx_b = _split_indices(orig_idx)
            reindex_start_num = base_int + 1
        sub_a = Subtitle(index=idx_a, start=sub.start, end=split_time, text=text_a)
        sub_b = Subtitle(index=idx_b, start=split_time, end=sub.end, text=text_b)
        self.subtitles[self.current_index:self.current_index + 1] = [sub_a, sub_b]
        self.stats_store.on_split(self.media_path, orig_idx, idx_a, idx_b)
        remap = self._reindex_after(self.current_index + 2, reindex_start_num)
        # 북마크: 원본 항목 북마크 → 첫 번째 분리 항목으로 이동
        bm_remap = dict(remap)
        bm_remap[orig_idx] = idx_a
        self.stats_store.remap_indices(self.media_path, remap)
        self.bookmark_store.remap_indices(self.media_path, bm_remap)
        self._bookmarks = self.bookmark_store.load(self.media_path)
        self._wrong_transcriptions = self.bookmark_store.load_wrong(self.media_path)
        self.srt_parser.save(self.srt_path, self.subtitles)
        self._refresh_display()
        self._play_current()

    def _split_time_from_word_timestamps(self, sub: "Subtitle", split_pos: int) -> float:
        """Find split time using flat word list from YAML.

        1. Estimate sentence start position in flat list using subtitle index.
        2. Use first 5 words of subtitle text to find exact sentence start.
        3. Return midpoint of (last_before.end, first_after.start) + MARGIN.
        Falls back to proportional estimate if word list is unavailable.
        """
        from .core.srt_parser import SRTParser
        margin = 0.0

        all_wts = self.all_word_timestamps
        text = sub.text
        text_a = text[:split_pos].rstrip()
        words_before = len(text_a.split())
        sub_words = text.split()

        def _proportional() -> float:
            ratio = words_before / len(sub_words) if sub_words else 0.5
            return sub.start + (sub.end - sub.start) * ratio

        if not all_wts:
            return _proportional()

        # Step 1: narrow flat list to words within this subtitle's time window
        tolerance = margin + 0.1
        sub_wts = [wt for wt in all_wts
                   if wt.start >= sub.start - tolerance and wt.end <= sub.end + tolerance]

        if not sub_wts:
            return _proportional()

        # Step 2: find sentence start via 5-word window match
        window = min(5, len(sub_words))
        sentence_start = None
        for i in range(len(sub_wts) - window + 1):
            if all(sub_wts[i + j].word == sub_words[j] for j in range(window)):
                sentence_start = i
                break

        if sentence_start is None:
            return _proportional()

        idx_before = sentence_start + words_before - 1
        idx_after = sentence_start + words_before

        if idx_before < len(sub_wts) and idx_after < len(sub_wts):
            return (sub_wts[idx_before].end + sub_wts[idx_after].start) / 2 + margin
        if idx_before < len(sub_wts):
            return sub_wts[idx_before].end
        return _proportional()

    _RESYNC_PADDING = 3.0        # seconds of extra audio to read after segment
    _RESYNC_START_PADDING = 6.0  # seconds of extra audio to read before segment start
    _RESYNC_MIN_MATCH = 0.6      # minimum match ratio for prefix/suffix anchor
    _RESYNC_ANCHOR_WORDS = 3     # number of leading/trailing words used for anchoring

    def _handle_sibilant(self, delta: float) -> None:
        """;/\'키: de_esser_reduction_db 값만 조정하고 재생바 아래에 현재 값을 표시한다."""
        import sys
        if not isinstance(self.player, PygameAudioPlayer):
            return
        new_val = self.player.adjust_de_esser(delta)
        self.settings_store.de_esser_reduction_db = new_val
        # 재생바 한 줄 아래에 힌트를 출력한 뒤 커서를 다시 올려
        # update_animation_line의 "\033[1A" 기준선을 유지한다.
        sys.stdout.write(
            f"\r\033[2K\033[2m         sibilant reduction: {new_val:.1f} dB\033[0m\n"
            "\033[1A"
        )
        sys.stdout.flush()

    def _handle_resync_timestamp(self, resync_start: bool = True, resync_end: bool = True) -> None:
        """W/E키: whisper-cli로 현재 구간 주변 오디오를 재분석하여 start/end timestamp 재조정."""
        if not self.subtitles:
            return
        sub = self.subtitles[self.current_index]

        # mp4인 경우 mp3 경로 추론
        media_path = self.media_path
        if Path(media_path).suffix.lower() == ".mp4":
            mp3_path = str(Path(media_path).with_suffix(".mp3"))
            if not Path(mp3_path).exists():
                self.ui.show_message("[red]MP3 파일 없음 (mp4→mp3 변환 필요)[/red]")
                self._refresh_display()
                return
            media_path = mp3_path

        start_pad = self._RESYNC_START_PADDING if resync_start else self._RESYNC_PADDING
        clip_start = max(0.0, sub.start - start_pad)
        clip_end = sub.end + self._RESYNC_PADDING

        self.ui.show_message("[dim]Resyncing timestamp with whisper-cli...[/dim]")
        if self.player:
            self.player.stop()

        import tempfile
        import subprocess
        import json as _json

        model_path = Path(__file__).parents[1] / "models" / "ggml-small.bin"
        if not model_path.exists():
            self.ui.show_message("[red]모델 파일 없음: models/ggml-small.bin[/red]")
            self._refresh_display()
            return

        with tempfile.TemporaryDirectory() as tmpdir:
            clip_path = str(Path(tmpdir) / "clip.mp3")
            # ffmpeg로 구간 추출
            ff = subprocess.run(
                [
                    "ffmpeg", "-y",
                    "-i", media_path,
                    "-ss", str(clip_start),
                    "-to", str(clip_end),
                    "-q:a", "0",
                    clip_path,
                ],
                capture_output=True,
            )
            if ff.returncode != 0:
                self.ui.show_message("[red]ffmpeg 구간 추출 실패[/red]")
                self._refresh_display()
                return

            # whisper-cli 실행 (word-level JSON)
            ws = subprocess.run(
                [
                    "whisper-cli",
                    "-m", str(model_path),
                    "-f", clip_path,
                    "--output-json-full",
                    "--split-on-word",
                    "--max-len", "1",
                    "--dtw", "tiny",
                    "--no-prints",
                ],
                capture_output=True,
                cwd=tmpdir,
            )
            if ws.returncode != 0:
                self.ui.show_message("[red]whisper-cli 실패[/red]")
                self._refresh_display()
                return

            json_path = Path(tmpdir) / "clip.mp3.json"
            if not json_path.exists():
                self.ui.show_message("[red]whisper 출력 파일 없음[/red]")
                self._refresh_display()
                return

            with open(json_path, encoding="utf-8", errors="replace") as f:
                data = _json.load(f)

        # word timestamp 파싱 (clip 내 상대 시간 → 절대 시간)
        words: list[tuple[str, float, float]] = []  # (word, abs_start, abs_end)
        for seg in data.get("transcription", []):
            text = seg.get("text", "").strip().strip('"')
            if not text or text.startswith("["):
                continue
            offsets = seg.get("offsets", {})
            rel_start = offsets.get("from", 0) / 1000.0
            rel_end = offsets.get("to", 0) / 1000.0
            words.append((text, clip_start + rel_start, clip_start + rel_end))

        if not words:
            self.ui.show_message("[red]whisper 결과에 단어 없음[/red]")
            self._refresh_display()
            return

        # 현재 자막 텍스트의 앞부분/뒷부분을 whisper 결과에서 찾아 start/end timestamp 결정
        sub_words = sub.text.split()
        if not sub_words:
            self._refresh_display()
            return

        def _norm(w: str) -> str:
            return w.lower().strip(".,!?;:\"'—-")

        w_norm = [_norm(w[0]) for w in words]
        s_norm = [_norm(w) for w in sub_words]

        def _find_sequence(target: list[str], from_idx: int = 0) -> tuple[int, float]:
            """target 단어 시퀀스가 w_norm[from_idx:] 에서 가장 잘 맞는 위치를 반환."""
            n = len(target)
            best_i, best_score = -1, 0.0
            for i in range(from_idx, len(w_norm) - n + 1):
                matched = sum(1 for j, t in enumerate(target) if w_norm[i + j] == t)
                score = matched / n
                if score > best_score:
                    best_score = score
                    best_i = i
            return best_i, best_score

        n_anchor = min(self._RESYNC_ANCHOR_WORDS, len(s_norm))
        prefix = s_norm[:n_anchor]
        suffix = s_norm[-n_anchor:]

        prev_end = self.subtitles[self.current_index - 1].end if self.current_index > 0 else 0.0
        next_start = self.subtitles[self.current_index + 1].start if self.current_index < len(self.subtitles) - 1 else float("inf")

        new_start = sub.start
        new_end = sub.end

        if resync_start:
            start_i, start_score = _find_sequence(prefix)
            if start_score < self._RESYNC_MIN_MATCH or start_i < 0:
                self.ui.show_message(f"[yellow]앞부분 매칭 실패 ({start_score:.0%}) — 미변경[/yellow]")
                self._refresh_display()
                return
            new_start = round(max(prev_end + 0.01, words[start_i][1]), 2)

        if resync_end:
            from_idx = 0 if not resync_start else start_i
            end_i, end_score = _find_sequence(suffix, from_idx=from_idx)
            if end_score < self._RESYNC_MIN_MATCH or end_i < 0:
                self.ui.show_message(f"[yellow]뒷부분 매칭 실패 ({end_score:.0%}) — 미변경[/yellow]")
                self._refresh_display()
                return
            new_end = round(min(next_start - 0.01, words[end_i + n_anchor - 1][2]), 2)

        if new_end <= new_start:
            self.ui.show_message("[red]재조정 결과가 유효하지 않음 — 미변경[/red]")
            self._refresh_display()
            return

        sub.start = new_start
        sub.end = new_end
        self.srt_parser.save(self.srt_path, self.subtitles)
        self._refresh_display()
        if resync_start and not resync_end:
            self._play_preview(sub.start, min(sub.end, sub.start + 1.0))
        elif resync_end and not resync_start:
            self._play_preview(max(sub.start, sub.end - 1.0), sub.end)
        else:
            self._play_current()

    def _handle_transcribe(self) -> None:
        if not self.subtitles:
            return
        sub = self.subtitles[self.current_index]
        # cbreak 모드 유지 - 입력 중 단축키(Option+key) 처리를 위해 직접 읽기
        buf: list[str] = []
        cursor_pos: int = 0
        blink_on: bool = True
        last_blink: float = time.time()
        self.ui.show_transcribe_prompt(buf, cursor_pos, init=True, show_cursor=True)

        while True:
            rlist, _, _ = select.select([self._fd], [], [], 0.1)
            if not rlist:
                now = time.time()
                if now - last_blink >= 0.5:
                    blink_on = not blink_on
                    last_blink = now
                    self.ui.show_transcribe_prompt(buf, cursor_pos, show_cursor=blink_on)
                continue
            ch = os.read(self._fd, 1)

            def _redraw(init: bool = False) -> None:
                nonlocal blink_on, last_blink
                blink_on = True
                last_blink = time.time()
                self.ui.show_transcribe_prompt(buf, cursor_pos, init=init, show_cursor=True)

            if ch in (b'\r', b'\n'):  # Enter → 제출
                break
            elif ch == b'\t':  # Tab → 처음부터 다시 재생
                self._refresh_display()
                self._play_current()
                _redraw(init=True)
            elif ch == b'\x1b':  # ESC 또는 escape sequence
                rlist2, _, _ = select.select([self._fd], [], [], 0.05)
                if not rlist2:
                    # 단독 ESC → 취소
                    sys.stdout.write("\033[?25l")
                    sys.stdout.flush()
                    self._refresh_display()
                    return
                ch2 = os.read(self._fd, 1)
                if ch2 == b'[':  # CSI sequence (화살표 키 등)
                    seq = b''
                    while True:
                        r3, _, _ = select.select([self._fd], [], [], 0.05)
                        if not r3:
                            break
                        ch3 = os.read(self._fd, 1)
                        seq += ch3
                        if 0x40 <= ch3[0] <= 0x7e:  # CSI final byte
                            break
                    if seq == b'D':  # ← 왼쪽 화살표
                        cursor_pos = max(0, cursor_pos - 1)
                        _redraw()
                    elif seq == b'C':  # → 오른쪽 화살표
                        cursor_pos = min(len(buf), cursor_pos + 1)
                        _redraw()
                    elif seq in (b'1;3D', b'1;9D'):  # Opt+← 단어 왼쪽
                        while cursor_pos > 0 and buf[cursor_pos - 1] == ' ':
                            cursor_pos -= 1
                        while cursor_pos > 0 and buf[cursor_pos - 1] != ' ':
                            cursor_pos -= 1
                        _redraw()
                    elif seq in (b'1;3C', b'1;9C'):  # Opt+→ 단어 오른쪽
                        while cursor_pos < len(buf) and buf[cursor_pos] == ' ':
                            cursor_pos += 1
                        while cursor_pos < len(buf) and buf[cursor_pos] != ' ':
                            cursor_pos += 1
                        _redraw()
                elif ch2 == b'b':  # Opt+← (emacs 스타일)
                    while cursor_pos > 0 and buf[cursor_pos - 1] == ' ':
                        cursor_pos -= 1
                    while cursor_pos > 0 and buf[cursor_pos - 1] != ' ':
                        cursor_pos -= 1
                    _redraw()
                elif ch2 == b'f':  # Opt+→ (emacs 스타일)
                    while cursor_pos < len(buf) and buf[cursor_pos] == ' ':
                        cursor_pos += 1
                    while cursor_pos < len(buf) and buf[cursor_pos] != ' ':
                        cursor_pos += 1
                    _redraw()
                elif ch2 == b'v':  # Opt+V → 자막 보이기/감추기
                    self._subtitle_masked = not self._subtitle_masked
                    self._refresh_display()
                    _redraw(init=True)
                # 그 외 escape sequence → 무시
            elif ch in (b'\x7f', b'\x08'):  # Backspace
                if cursor_pos > 0:
                    buf.pop(cursor_pos - 1)
                    cursor_pos -= 1
                    _redraw()
            else:
                char = ch.decode('utf-8', errors='ignore')
                if char.isprintable():
                    buf.insert(cursor_pos, char)
                    cursor_pos += 1
                    _redraw()

        sys.stdout.write("\033[?25l")
        sys.stdout.flush()
        user_input = ''.join(buf).strip()
        if not user_input:
            self._refresh_display()
            return
        is_correct = self.ui.show_transcribe_result(sub.text, user_input)
        if is_correct:
            self.bookmark_store.remove_wrong(self.media_path, sub.index)
        else:
            self.bookmark_store.add_wrong(self.media_path, sub.index)
        self._wrong_transcriptions = self.bookmark_store.load_wrong(self.media_path)
        self._refresh_display()
        self.ui.show_transcribe_prompt(buf, len(buf), init=True)
        self.ui.show_transcribe_result(sub.text, user_input)

        # 결과 표시 후 Tab(재생), Opt+V(자막 토글), 이동 처리 루프
        def _nav_prev():
            if self._mode == "R":
                self._handle_review_prev()
            else:
                self._handle_prev()

        def _nav_next():
            if self._mode == "R":
                self._handle_review_next()
            else:
                self._handle_next()

        def _nav_page(direction: int):
            if self._mode == "R":
                self._handle_review_page(direction)
            else:
                self._handle_l_page(direction)

        while True:
            rlist, _, _ = select.select([self._fd], [], [], 0.1)
            if not rlist:
                continue
            ch = os.read(self._fd, 1)
            if ch in (b'\t', b' '):  # Tab / Space → 다시 재생
                self._refresh_display()
                self._play_current()
                self.ui.show_transcribe_prompt(buf, len(buf), init=True)
                self.ui.show_transcribe_result(sub.text, user_input)
            elif ch in (b'\r', b'\n', b't', b'T'):  # Enter / T → 종료
                self._refresh_display()
                return
            elif ch in (b'q', b'Q'):  # Q → 앱 종료
                self._handle_quit()
                sys.exit(0)
            elif ch == b'\x1b':  # ESC 또는 escape sequence
                rlist2, _, _ = select.select([self._fd], [], [], 0.05)
                if not rlist2:
                    # 단독 ESC → 종료
                    self._refresh_display()
                    return
                ch2 = os.read(self._fd, 1)
                if ch2 == b'[':  # CSI sequence (화살표 키 등)
                    rlist3, _, _ = select.select([self._fd], [], [], 0.05)
                    if rlist3:
                        ch3 = os.read(self._fd, 1)
                        if ch3 in (b'A', b'D'):  # ↑/← → 이전
                            self._refresh_display()
                            _nav_prev()
                            return
                        if ch3 in (b'B', b'C'):  # ↓/→ → 다음
                            self._refresh_display()
                            _nav_next()
                            return
                    # 기타 CSI → 무시
                elif ch2 == b'v':  # Opt+V → 자막 보이기/감추기
                    self._subtitle_masked = not self._subtitle_masked
                    self._refresh_display()
                    self.ui.show_transcribe_prompt(buf, len(buf), init=True)
                    self.ui.show_transcribe_result(sub.text, user_input)
                # 그 외 escape sequence → 무시
            elif ch in (b'a', b'A', b'k', b'K'):  # A/K → 이전
                self._refresh_display()
                _nav_prev()
                return
            elif ch in (b'd', b'D', b'j', b'J'):  # D/J → 다음
                self._refresh_display()
                _nav_next()
                return
            elif ch == b'[':  # [ → 이전 3
                self._refresh_display()
                _nav_page(-1)
                return
            elif ch == b']':  # ] → 다음 3
                self._refresh_display()
                _nav_page(1)
                return
            elif ch in (b'v', b'V'):  # V → 자막 보이기/감추기
                self._subtitle_masked = not self._subtitle_masked
                self._refresh_display()
                self.ui.show_transcribe_prompt(buf, len(buf), init=True)
                self.ui.show_transcribe_result(sub.text, user_input)
            # 그 외 키 → 무시

    def _reindex_subtitles(self) -> None:
        for i, sub in enumerate(self.subtitles):
            sub.index = str(i + 1)

    def _heal_stale_bookmarks(self) -> None:
        """북마크/틀린받아쓰기 인덱스가 현재 자막 목록에 없으면 분리된 첫 번째 자막으로 자동 보정."""
        sub_map = {sub.index: sub for sub in self.subtitles}
        stale = {idx for idx in self._bookmarks | self._wrong_transcriptions if idx not in sub_map}
        if not stale:
            return
        remap = {}
        for idx in stale:
            for sub in self.subtitles:
                if sub.index.startswith(idx + "-"):
                    remap[idx] = sub.index
                    break
        if remap:
            self.bookmark_store.remap_indices(self.media_path, remap)
            self._bookmarks = self.bookmark_store.load(self.media_path)
            self._wrong_transcriptions = self.bookmark_store.load_wrong(self.media_path)

    def _reindex_after(self, start_pos: int, start_num: int) -> dict[str, str]:
        """start_pos 이후 자막의 앞 번호(base)를 start_num부터 재지정. suffix(-1/-2/...)는 유지.

        base 번호가 바뀔 때만 카운터를 증가시켜 동일 base의 suffix 항목들을 같은 번호로 묶는다.
        예: [383-1, 383-2, 384] → start_num=382 → [382-1, 382-2, 383]
        """
        remap: dict[str, str] = {}
        new_base = start_num
        prev_old_base: str | None = None
        for i in range(start_pos, len(self.subtitles)):
            old_idx = self.subtitles[i].index
            parts = old_idx.split('-')
            old_base = parts[0]
            suffix = parts[1:]
            if old_base != prev_old_base:
                if prev_old_base is not None:
                    new_base += 1
                prev_old_base = old_base
            new_idx = '-'.join([str(new_base)] + suffix)
            if old_idx != new_idx:
                remap[old_idx] = new_idx
                self.subtitles[i].index = new_idx
        return remap

    def _handle_bookmark_toggle(self) -> None:
        if not self.subtitles:
            return
        sub_index = self.subtitles[self.current_index].index
        self.bookmark_store.toggle(self.media_path, sub_index)
        self._bookmarks = self.bookmark_store.load(self.media_path)
        self._wrong_transcriptions = self.bookmark_store.load_wrong(self.media_path)
        self._refresh_display()

    def _handle_bookmark_list(self) -> None:
        if not self.subtitles:
            return
        self._heal_stale_bookmarks()
        bookmark_indices = sorted(self._bookmarks | self._wrong_transcriptions, key=_index_key)
        if not bookmark_indices:
            self._refresh_display()
            self.ui.show_message("[dim]No bookmarks or wrong transcriptions yet.[/dim]")
            return
        sub_map = {sub.index: sub for sub in self.subtitles}
        play_counts = self.stats_store.load(self.media_path).subtitle_play_counts
        # 커서를 현재 구간과 가장 가까운 북마크 위치로 초기화
        current_sub_index = self.subtitles[self.current_index].index
        closest = min(range(len(bookmark_indices)), key=lambda i: abs(_index_key(bookmark_indices[i])[0] - _index_key(current_sub_index)[0]))
        self._bookmark_cursor = closest
        self._bookmark_page = closest // 10
        self._showing_bookmarks = True
        self.ui.clear()
        self.ui.show_bookmark_list(bookmark_indices, sub_map, self._bookmark_page, self._bookmark_cursor,
                                    current_sub_index=current_sub_index, play_counts=play_counts,
                                    wrong_transcriptions=self._wrong_transcriptions)

    def _handle_bookmark_cursor(self, direction: int) -> None:
        bookmark_indices = sorted(self._bookmarks | self._wrong_transcriptions, key=_index_key)
        if not bookmark_indices:
            return
        self._bookmark_cursor = max(0, min(len(bookmark_indices) - 1, self._bookmark_cursor + direction))
        self._bookmark_page = self._bookmark_cursor // 10
        sub_map = {sub.index: sub for sub in self.subtitles}
        play_counts = self.stats_store.load(self.media_path).subtitle_play_counts
        self.ui.clear()
        self.ui.show_bookmark_list(bookmark_indices, sub_map, self._bookmark_page, self._bookmark_cursor,
                                    current_sub_index=self.subtitles[self.current_index].index,
                                    play_counts=play_counts,
                                    wrong_transcriptions=self._wrong_transcriptions)

    def _handle_bookmark_page(self, direction: int) -> None:
        bookmark_indices = sorted(self._bookmarks | self._wrong_transcriptions, key=_index_key)
        if not bookmark_indices:
            return
        page_count = max(1, -(-len(bookmark_indices) // 10))
        new_page = self._bookmark_page + direction
        if new_page < 0:
            self.ui.show_message("[red]This is the first page.[/red]")
            return
        if new_page >= page_count:
            self.ui.show_message("[red]This is the last page.[/red]")
            return
        self._bookmark_page = new_page
        self._bookmark_cursor = new_page * 10  # 페이지 첫 항목으로 커서 이동
        sub_map = {sub.index: sub for sub in self.subtitles}
        play_counts = self.stats_store.load(self.media_path).subtitle_play_counts
        self.ui.clear()
        self.ui.show_bookmark_list(bookmark_indices, sub_map, self._bookmark_page, self._bookmark_cursor,
                                    current_sub_index=self.subtitles[self.current_index].index,
                                    play_counts=play_counts,
                                    wrong_transcriptions=self._wrong_transcriptions)

    def _handle_bookmark_select(self) -> None:
        """Enter: 선택한 북마크 구간으로 이동하고 LR모드로 복귀."""
        bookmark_indices = sorted(self._bookmarks | self._wrong_transcriptions, key=_index_key)
        if not bookmark_indices or self._bookmark_cursor >= len(bookmark_indices):
            self._showing_bookmarks = False
            self._refresh_display()
            return
        target_sub_index = bookmark_indices[self._bookmark_cursor]
        # 1-based subtitle index → 0-based list index
        target_list_index = next(
            (i for i, s in enumerate(self.subtitles) if s.index == target_sub_index),
            None,
        )
        self._showing_bookmarks = False
        if target_list_index is not None:
            self._save_back()
            self.current_index = target_list_index
            if self._mode == "R":
                self._mode = "LR"
        self._refresh_display()
        self._play_current()

    def _handle_stats_cursor(self, direction: int) -> None:
        """통계 화면 커서 이동."""
        total = len(self._stats_ranked)
        if total == 0:
            return
        self._stats_cursor = max(0, min(total - 1, self._stats_cursor + direction))
        self._stats_page = self._stats_cursor // 10
        progress_pct = (self.current_index + 1) / len(self.subtitles) * 100
        self.ui.clear()
        self.ui.show_stats_header()
        self.ui.show_learning_stats(
            self._stats_ranked, self._stats_sub_map, self._stats_total_seconds,
            self._stats_page, progress_pct,
            current_sub_index=self.subtitles[self.current_index].index,
            bookmarks=self._bookmarks,
            cursor=self._stats_cursor,
            wrong_transcriptions=self._wrong_transcriptions,
        )

    def _handle_stats_select(self) -> None:
        """Enter: 선택한 통계 항목 구간으로 이동하고 LR모드로 복귀."""
        if not self._stats_ranked or self._stats_cursor >= len(self._stats_ranked):
            self._showing_stats = False
            self._refresh_display()
            return
        target_sub_index = self._stats_ranked[self._stats_cursor][0]
        target_list_index = next(
            (i for i, s in enumerate(self.subtitles) if s.index == target_sub_index),
            None,
        )
        self._showing_stats = False
        if target_list_index is not None:
            self._save_back()
            self.current_index = target_list_index
            if self._mode == "R":
                self._mode = "LR"
        self._refresh_display()
        self._play_current()

    def _handle_print_stats(self) -> None:
        if not self.subtitles:
            return
        stats = self.stats_store.load(self.media_path)
        self._stats_sub_map = {sub.index: sub for sub in self.subtitles}
        self._stats_ranked = sorted(
            stats.subtitle_play_counts.items(),
            key=lambda x: _index_key(x[0]),  # 자막 순번 오름차순
        )
        self._stats_total_seconds = sum(
            (self._stats_sub_map[idx].end - self._stats_sub_map[idx].start) * count
            for idx, count in stats.subtitle_play_counts.items()
            if idx in self._stats_sub_map
        )
        progress_pct = (self.current_index + 1) / len(self.subtitles) * 100
        # 현재 학습 중인 자막 순번에 가장 가까운 위치의 페이지로 이동
        import bisect
        current_sub_index = self.subtitles[self.current_index].index
        ranked_indices = [idx for idx, _ in self._stats_ranked]
        ranked_keys = [_index_key(idx) for idx in ranked_indices]
        pos = bisect.bisect_right(ranked_keys, _index_key(current_sub_index)) - 1
        self._stats_cursor = max(0, pos)
        self._stats_page = self._stats_cursor // 10
        self.ui.clear()
        self.ui.show_stats_header()
        self.ui.show_learning_stats(
            self._stats_ranked, self._stats_sub_map, self._stats_total_seconds,
            self._stats_page, progress_pct,
            current_sub_index=current_sub_index,
            bookmarks=self._bookmarks,
            cursor=self._stats_cursor,
            wrong_transcriptions=self._wrong_transcriptions,
        )

    def _handle_date_stats_cursor(self, direction: int) -> None:
        page_size = 3
        total = len(self._date_stats_entries)
        page_count = max(1, -(-total // page_size))
        current_page_size = min(page_size, total - self._date_stats_page * page_size)

        new_cursor = self._date_stats_cursor + direction

        if new_cursor < 0:
            if self._date_stats_page > 0:
                self._date_stats_page -= 1
                prev_size = min(page_size, total - self._date_stats_page * page_size)
                self._date_stats_cursor = prev_size - 1
            else:
                self.ui.show_message("[red]This is the first date.[/red]")
                return
        elif new_cursor >= current_page_size:
            if self._date_stats_page < page_count - 1:
                self._date_stats_page += 1
                self._date_stats_cursor = 0
            else:
                self.ui.show_message("[red]This is the last date.[/red]")
                return
        else:
            self._date_stats_cursor = new_cursor

        progress_pct = (self.current_index + 1) / len(self.subtitles) * 100
        self.ui.clear()
        self.ui.show_date_stats_header()
        self.ui.show_date_stats(
            self._date_stats_entries, self._stats_sub_map,
            self._date_stats_page, progress_pct, cursor=self._date_stats_cursor,
        )

    def _handle_print_date_stats(self) -> None:
        if not self.subtitles:
            return
        sub_map = {sub.index: sub for sub in self.subtitles}
        self._stats_sub_map = sub_map
        self._date_stats_entries = self.stats_store.load_date_stats(self.media_path)
        self._date_stats_page = 0
        self._date_stats_cursor = 0
        progress_pct = (self.current_index + 1) / len(self.subtitles) * 100
        self.ui.clear()
        self.ui.show_date_stats_header()
        self.ui.show_date_stats(
            self._date_stats_entries, sub_map, self._date_stats_page, progress_pct,
            cursor=self._date_stats_cursor,
        )

    def _handle_stats_page(self, direction: int) -> None:
        progress_pct = (self.current_index + 1) / len(self.subtitles) * 100
        if self._showing_date_stats:
            total = len(self._date_stats_entries)
            page_count = max(1, -(-total // 3))
            new_page = self._date_stats_page + direction
            if new_page < 0:
                self.ui.show_message("[red]This is the first page.[/red]")
                return
            if new_page >= page_count:
                self.ui.show_message("[red]This is the last page.[/red]")
                return
            self._date_stats_page = new_page
            self._date_stats_cursor = 0
            self.ui.clear()
            self.ui.show_date_stats_header()
            self.ui.show_date_stats(
                self._date_stats_entries, self._stats_sub_map, self._date_stats_page, progress_pct,
                cursor=self._date_stats_cursor,
            )
            return
        if not self._stats_ranked:
            return
        page_count = max(1, -(-len(self._stats_ranked) // 10))  # ceil division
        new_page = self._stats_page + direction
        if new_page < 0:
            self.ui.show_message("[red]This is the first page.[/red]")
            return
        if new_page >= page_count:
            self.ui.show_message("[red]This is the last page.[/red]")
            return
        self._stats_page = new_page
        self._stats_cursor = new_page * 10  # 페이지 첫 항목으로 커서 이동
        self.ui.clear()
        self.ui.show_stats_header()
        self.ui.show_learning_stats(
            self._stats_ranked, self._stats_sub_map, self._stats_total_seconds,
            self._stats_page, progress_pct,
            current_sub_index=self.subtitles[self.current_index].index,
            bookmarks=self._bookmarks,
            cursor=self._stats_cursor,
            wrong_transcriptions=self._wrong_transcriptions,
        )

    def _refresh_display(self) -> None:
        self.ui.clear()
        self.ui.show_study_header(self._mode)
        title = Path(self.media_path).stem if self.media_path else ""
        if self._mode == "R" and self._review_list:
            review_subs = [self.subtitles[i] for i in self._review_list]
            self.ui.show_subtitles(review_subs, self._review_index, masked=self._subtitle_masked, review_total=len(self._review_list), bookmarks=self._bookmarks, title=title, wrong_transcriptions=self._wrong_transcriptions)
        else:
            self.ui.show_subtitles(self.subtitles, self.current_index, masked=self._subtitle_masked, bookmarks=self._bookmarks, title=title, wrong_transcriptions=self._wrong_transcriptions)
        if self.player and self.player.is_playing() and self._play_duration > 0:
            elapsed = time.monotonic() - self._play_start_time
            progress = min(1.0, elapsed / self._play_duration)
            self.ui.show_animation_line(progress, dim=False)
        elif self._paused and self._play_duration > 0:
            self.ui.show_animation_line(self._paused_progress, dim=True)
        else:
            self.ui.show_animation_line(0.0, dim=True)
