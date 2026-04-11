import os
import select as _select
import sys
import termios
import tty
from pathlib import Path

from rich.console import Console
from rich.panel import Panel
from rich.text import Text

from .core.models import Session, Subtitle

console = Console()


class RichUI:
    # ── 헤더 ──────────────────────────────────────────────────────────────────
    _HEADER_TEXT = (
        "[bold cyan]LangRepeater[/bold cyan]\n"
        "Audio segment repeater for language learning"
    )

    # ── 모드 선택 줄 ──────────────────────────────────────────────────────────
    _MODE_LINE_L = (
        "[dim]1: Review [/dim]  |  "
        "[dim]2: Listen & Repeat [/dim]  |  "
        "[bold yellow]3: Listening [/bold yellow]"
    )
    _MODE_LINE_R = (
        "[bold green]1: Review [/bold green]  |  "
        "[dim]2: Listen & Repeat [/dim]  |  "
        "[dim]3: Listening [/dim]"
    )
    _MODE_LINE_LR = (
        "[dim]1: Review [/dim]  |  "
        "[bold white]2: Listen & Repeat [/bold white]  |  "
        "[dim]3: Listening [/dim]"
    )

    # ── 도움말 텍스트 ─────────────────────────────────────────────────────────
    _HELP_TEXT_L = (
        "[dim]Space: play/pause      |  A/←/↑: prev         |  D/→/↓: next   |  [ ]: prev/next 3 [/dim]\n"
        "[dim]V: show/hide subtitle  |  G: goto             |  Q: quit       |  ESC: home        [/dim]\n"
        "[dim]                       |                      |                |                   [/dim]\n"
        "[dim]                       |                      |                |                   [/dim]\n"
        "[dim]                       |                      |                |                   [/dim]"
    )
    _HELP_TEXT_LR = (
        "[dim]Space: play/pause      |  A/←/↑: prev         |  D/→/↓: next   |  [ ]: prev/next 3 [/dim]\n"
        "[dim]V: show/hide subtitle  |  G: goto             |  Q: quit       |  ESC: home        [/dim]\n"
        "[dim]S: replay              |  [/dim][white]T: transcribe[/white][dim]       |  U: merge      |  I: split         [/dim]\n"
        "[dim]Z: start -0.1s         |  X: start +0.1s      |  ,: end -0.1s  |  .: end +0.1s     [/dim]\n"
        "[dim]P: segment stats       |  0: date stats       |  B: bookmark   |  -: bookmark list [/dim]"
    )
    _HELP_TEXT_R = (
        "[dim]Space: play/pause      |  A/←/↑: prev         |  D/→/↓: next   |  [ ]: prev/next 3 [/dim]\n"
        "[dim]V: show/hide subtitle  |  [/dim][white]R: resample[/white][dim]         |  Q: quit       |  ESC: home        [/dim]\n"
        "[dim]S: replay              |  T: transcribe       |                |                   [/dim]\n"
        "[dim]Z: start -0.1s         |  X: start +0.1s      |  ,: end -0.1s  |  .: end +0.1s     [/dim]\n"
        "[dim]P: segment stats       |  0: date stats       |  B: bookmark   |                   [/dim]"
    )
    _HELP_TEXT_STATS = "[dim]↑/↓: move  |  Enter: go  |  [ ]: prev/next page  |  any key: back[/dim]"

    # ── 메뉴 힌트 ─────────────────────────────────────────────────────────────
    _HINT_MENU     = "[dim]↑/↓: move  |  Enter: select  |  ESC: back[/dim]"
    _HINT_HOME     = "[dim]↑/↓: move  |  Enter: select  |  Q: quit[/dim]"
    _HINT_BOOKMARK = "[dim]↑/↓: move  |  Enter: go  |  [ ]: prev/next page  |  any key: back[/dim]"

    # ── 통계 화면 컬럼 헤더 ───────────────────────────────────────────────────
    _STATS_SEG_HEADER  = "[bold white]     #     repeats  sentence[/bold white]"
    _STATS_DATE_HEADER = "[bold white]               segments  repeats   net play time[/bold white]"

    # ── 받아쓰기 힌트 / 범례 ──────────────────────────────────────────────────
    _TRANSCRIBE_HINT = (
        "Transcribe [Tab: play | Opt+V: show/hide subtitle | ESC/Enter: return]"
    )
    _TRANSCRIBE_HINT_RESULT = (
        "Transcribe [Tab/Space: play | V/Opt+V: show/hide subtitle | ESC/Enter: return]"
    )
    _TRANSCRIBE_LEGEND = (
        "      \033[1;32m█\033[0m\033[2m correct  "
        "\033[0m\033[1;33m█\033[0m\033[2m case/punct  "
        "\033[0m\033[1;31m█\033[0m\033[2m wrong\033[0m"
    )

    # ── 기타 ──────────────────────────────────────────────────────────────────
    _VISIBLE_PUNCT = frozenset(".,;:?!-'")

    # ─────────────────────────────────────────────────────────────────────────

    def clear(self) -> None:
        console.clear()

    def show_welcome(self) -> None:
        """Home screen header: clear screen, then program name + description."""
        console.clear()
        console.print(Panel(self._HEADER_TEXT, expand=False))

    def show_study_header(self, mode: str = "LR") -> None:
        """Study screen header: program name + description + mode + key bindings."""
        if mode == "L":
            mode_line = self._MODE_LINE_L
            help_text = self._HELP_TEXT_L
        elif mode == "R":
            mode_line = self._MODE_LINE_R
            help_text = self._HELP_TEXT_R
        else:
            mode_line = self._MODE_LINE_LR
            help_text = self._HELP_TEXT_LR
        border_style = "yellow" if mode == "L" else "green" if mode == "R" else ""
        console.print(Panel(
            self._HEADER_TEXT + "\n\n" + mode_line + "\n\n" + help_text,
            expand=False,
            border_style=border_style,
        ))

    def _run_menu(
        self,
        items: list[str],
        dim_items: list[str] | None = None,
        *,
        draw_fn,
        selected: int = 0,
        allow_quit: bool = False,
        hint: str = "",
    ) -> int | None:
        """화살표키 인터랙티브 메뉴. 선택 시 index(0-based), 취소 시 None, Q 종료 시 -1 반환.
        dim_items: 비선택 시 표시할 별도 문자열 목록. None이면 items를 [dim]으로 감싸서 표시."""
        _hint = hint if hint else self._HINT_MENU

        def _render(sel: int) -> None:
            draw_fn()
            console.print()
            for i, item in enumerate(items):
                if i == sel:
                    console.print(f"  [bold magenta]▶︎[/bold magenta] {item}")
                else:
                    dim_item = dim_items[i] if dim_items else f"[dim]{item}[/dim]"
                    console.print(f"    {dim_item}")
            if _hint:
                console.print(f"\n{_hint}")

        selected = max(0, min(len(items) - 1, selected))
        _render(selected)

        fd = sys.stdin.fileno()
        old = termios.tcgetattr(fd)
        try:
            tty.setcbreak(fd)
            while True:
                rlist, _, _ = _select.select([fd], [], [], 1.0)
                if not rlist:
                    continue
                ch = os.read(fd, 1)

                if ch == b'\x1b':
                    r2, _, _ = _select.select([fd], [], [], 0.05)
                    if not r2:
                        return None  # bare ESC
                    ch2 = os.read(fd, 1)
                    if ch2 == b'[':
                        r3, _, _ = _select.select([fd], [], [], 0.05)
                        if r3:
                            ch3 = os.read(fd, 1)
                            if ch3 == b'A':   # ↑
                                selected = max(0, selected - 1)
                                _render(selected)
                            elif ch3 == b'B': # ↓
                                selected = min(len(items) - 1, selected + 1)
                                _render(selected)
                elif ch in (b'\r', b'\n'):
                    return selected
                elif allow_quit and ch in (b'q', b'Q'):
                    return -1
        finally:
            termios.tcsetattr(fd, termios.TCSADRAIN, old)

    def show_file_list(self, files: list[str], prompt: str) -> int | None:
        def _header():
            self.show_welcome()
            console.print(f"\n[bold]{prompt}[/bold]")

        items = [Path(f).name for f in files]
        return self._run_menu(items, draw_fn=_header)

    @staticmethod
    def _mask_word(word: str) -> str:
        return "".join(c if c in RichUI._VISIBLE_PUNCT else "_" for c in word)

    @staticmethod
    def _mask_text(text: str) -> str:
        """Return text with middle words masked, keeping first/last word and punctuation (,;:?!-) visible."""
        words = text.split()
        if len(words) <= 2:
            return text
        return words[0] + " " + " ".join(RichUI._mask_word(w) for w in words[1:-1]) + " " + words[-1]

    def show_subtitles(self, subtitles: list[Subtitle], current_index: int, masked: bool = True, review_total: int | None = None, bookmarks: set[int] | None = None) -> None:
        n = len(subtitles)
        # determine which 3 to display
        if n == 0:
            return
        if n == 1:
            indices = [0]
        elif n == 2:
            indices = [0, 1]
        else:
            if current_index == 0:
                indices = [0, 1, 2]
            elif current_index == n - 1:
                indices = [n - 3, n - 2, n - 1]
            else:
                indices = [current_index - 1, current_index, current_index + 1]

        # show progress info
        total_num_blocks = 51
        if review_total is not None:
            display_current = current_index + 1
            display_total = review_total
        else:
            display_current = current_index + 1
            display_total = n
        progress_pct = display_current / display_total * 100
        filled = round(progress_pct / 100 * total_num_blocks)
        bar = "█" * filled + "░" * (total_num_blocks - filled)
        console.print(
            f"\n [dim]Progress: {display_current}/{display_total} ({progress_pct:.1f}%)  {bar}[/dim]"
        )

        console.print()
        for idx in indices:
            sub = subtitles[idx]
            display_text = self._mask_text(sub.text) if masked else sub.text
            bm_marker = "  *  " if (bookmarks and sub.index in bookmarks) else "     "
            if idx == current_index:
                ts = f"[{sub.start:.2f}s ~ {sub.end:.2f}s]"
                line = Text()
                line.append(f"{sub.index:>4}", style="bold cyan")
                line.append(bm_marker, style="bold yellow")
                line.append(display_text, style="bold white")
                line.append(f"  {ts}", style="dim bold cyan")
                console.print(line)
            else:
                bm_str = f"[dim bold yellow]{bm_marker}[/dim bold yellow]" if (bookmarks and sub.index in bookmarks) else bm_marker
                console.print(f"[dim cyan]{sub.index:>4}[/dim cyan]{bm_str}[dim white]{display_text}[/dim white]")

    def show_home_menu(self, has_sessions: bool) -> str:
        """Show home menu. Returns: 'resume'|'new'|'url'|'delete'|'quit'."""
        items: list[str] = []
        keys: list[str] = []
        if has_sessions:
            items.append("Continue previous session")
            keys.append("resume")
        items.append("Open a new file")
        keys.append("new")
        items.append("Enter URL")
        keys.append("url")
        if has_sessions:
            items.append("Delete a session")
            keys.append("delete")

        def _header():
            console.clear()
            console.print(Panel(self._HEADER_TEXT, expand=False))

        result = self._run_menu(
            items, draw_fn=_header, allow_quit=True, hint=self._HINT_HOME,
        )
        if result is None or result == -1:
            return "quit"
        return keys[result]

    def ask_resume_session(self, sessions: list[Session]) -> int | None:
        """Show session list for resuming. Returns index or None to cancel."""
        bar_width = 20

        def _stem(path: str) -> str:
            name = Path(path).stem
            if len(name) > 40:
                name = name[:18] + "..." + name[-19:]
            return name

        def _bar(s: Session, bright: bool) -> str:
            if s.total_segments > 0:
                pct = min(1.0, (s.current_index + 1) / s.total_segments)
                filled = round(pct * bar_width)
            else:
                filled = 0
            empty = bar_width - filled
            color = "green" if bright else "dim green"
            return f"[{color}]{'█' * filled}[/{color}][dim]{'░' * empty}[/dim]"

        def _line(s: Session, bright: bool) -> str:
            name = _stem(s.media_path)
            return f"{name:<40}  {_bar(s, bright)}"

        items     = [_line(s, bright=True)  for s in sessions]
        dim_items = [_line(s, bright=False) for s in sessions]

        def _header():
            self.show_welcome()
            console.print("\n[bold]Select session to resume:[/bold]")

        return self._run_menu(items, dim_items, draw_fn=_header)

    def ask_delete_session(self, sessions: list[Session]) -> int | None:
        items = [
            f"{Path(s.media_path).name}  [dim](segment {s.current_index + 1})[/dim]"
            for s in sessions
        ]

        def _header():
            self.show_welcome()
            console.print("\n[bold]Select session to delete:[/bold]")

        return self._run_menu(items, draw_fn=_header)

    def confirm_delete(self, session: Session) -> bool:
        name = Path(session.media_path).name
        items = ["Yes, delete", "Cancel"]

        def _header():
            self.show_welcome()
            console.print(f"\nDelete [bold]{name}[/bold]?")

        result = self._run_menu(items, draw_fn=_header, selected=1)
        return result == 0

    @staticmethod
    def _open_file_dialog(initial_dir: str = "~") -> str | None:
        """Open native macOS file picker dialog for mp3/mp4 files via osascript."""
        import subprocess

        abs_dir = os.path.abspath(os.path.expanduser(initial_dir))
        script = (
            f'POSIX path of (choose file with prompt "Select an mp3 or mp4 file" '
            f'default location POSIX file "{abs_dir}")'
        )
        try:
            result = subprocess.run(
                ["osascript", "-e", script],
                capture_output=True, text=True, timeout=120,
            )
            if result.returncode == 0:
                return result.stdout.strip()
            return None
        except Exception:
            return None

    def ask_folder(self, previous_dir: str) -> str | None:
        items = [
            f"Same folder: [dim]{previous_dir}[/dim]",
            "Different folder",
        ]

        def _header():
            self.show_welcome()
            console.print("\n[bold]Select folder:[/bold]")

        while True:
            result = self._run_menu(items, draw_fn=_header)
            if result is None:
                return None
            if result == 0:
                return previous_dir
            # result == 1: open file dialog
            path = self._open_file_dialog(previous_dir)
            if path is not None:
                return path
            # dialog cancelled → loop back to menu

    def ask_split_point(self, subtitle, fd: int) -> int | None:
        """Show split point candidates. Returns char position or None to cancel."""
        import json
        import re
        text = subtitle.text

        # Detect language and load matching rules from split_points.json
        _is_ja = any('\u3000' <= c <= '\u9fff' or '\uf900' <= c <= '\ufaff' for c in text)
        _lang = "ja" if _is_ja else "en"
        _json_path = Path(__file__).parent / "split_points.json"
        try:
            with open(_json_path, encoding="utf-8") as _f:
                _all_rules = json.load(_f)
            _rules = _all_rules.get(_lang, {})
        except Exception:
            _rules = {}
        _after_chars = [c for c in _rules.get("after", []) if len(c) == 1]
        _before_words = _rules.get("before", [])

        # Find candidate split positions
        positions: list[int] = []

        # after: split after each listed character (followed by optional whitespace)
        for ch in _after_chars:
            pattern = re.escape(ch) + r'\s*'
            for m in re.finditer(pattern, text):
                pos = m.end()
                if 0 < pos < len(text) and pos not in positions:
                    positions.append(pos)

        # before: split before each listed word/phrase
        for phrase in _before_words:
            pattern = r'\b' + re.escape(phrase) + r'\b'
            for m in re.finditer(pattern, text, re.IGNORECASE):
                pos = m.start()
                if 0 < pos < len(text) and pos not in positions:
                    positions.append(pos)
        positions = sorted(set(positions))
        if not positions:
            console.print("[yellow]No split points found.[/yellow]")
            return None
        console.print("\n[bold]Select split point:[/bold]")
        line = Text()
        prev = 0
        for i, pos in enumerate(positions, 1):
            line.append(text[prev:pos])
            line.append(f"({i}) ", style="bold red")
            prev = pos
        line.append(text[prev:])
        console.print(line)
        console.print(f"\n[dim]Press 1-{len(positions)} to split, or ESC to cancel[/dim]")
        while True:
            ch = os.read(fd, 1).decode("utf-8", errors="ignore")
            if ch.lower() == "\x1b":
                return None
            if ch.isdigit():
                n = int(ch)
                if 1 <= n <= len(positions):
                    return positions[n - 1]

    @staticmethod
    def _make_animation_bar(progress: float, width: int = 20) -> str:
        """Build ─●─ style bar where ● slides left to right as progress goes 0→1."""
        pos = min(width - 1, max(0, round(progress * (width - 1))))
        return "─" * pos + "●" + "─" * (width - 1 - pos)

    def show_animation_line(self, progress: float = 0.0, dim: bool = True) -> None:
        """Print animation bar as a new line (call after show_subtitles)."""
        bar = self._make_animation_bar(progress)
        if dim:
            sys.stdout.write(f"\n\033[2m         {bar}\033[0m\n")
        else:
            sys.stdout.write(f"\n         {bar}\n")
        sys.stdout.flush()

    def update_animation_line(self, progress: float, dim: bool = False) -> None:
        """Overwrite animation bar in-place (cursor must be on the line after the bar)."""
        bar = self._make_animation_bar(progress)
        if dim:
            sys.stdout.write(f"\033[1A\r\033[2K\033[2m         {bar}\033[0m\n")
        else:
            sys.stdout.write(f"\033[1A\r\033[2K         {bar}\n")
        sys.stdout.flush()

    def show_message(self, msg: str) -> None:
        console.print(msg)

    def wait_for_enter(self) -> None:
        """Enter 키 입력을 기다린다."""
        fd = sys.stdin.fileno()
        old = termios.tcgetattr(fd)
        try:
            tty.setcbreak(fd)
            while True:
                rlist, _, _ = _select.select([fd], [], [], 1.0)
                if not rlist:
                    continue
                ch = os.read(fd, 1)
                if ch in (b'\r', b'\n', b'\x1b'):
                    break
        finally:
            termios.tcsetattr(fd, termios.TCSADRAIN, old)

    def ask_path(self, prompt: str) -> str | None:
        """텍스트 입력 프롬프트. ESC로 취소, Enter로 확정."""
        sys.stdout.write(f"{prompt}: ")
        sys.stdout.flush()
        buf: list[str] = []
        fd = sys.stdin.fileno()
        old = termios.tcgetattr(fd)
        try:
            tty.setcbreak(fd)
            while True:
                rlist, _, _ = _select.select([fd], [], [], 1.0)
                if not rlist:
                    continue
                ch = os.read(fd, 1)
                if ch in (b'\r', b'\n'):
                    sys.stdout.write('\n')
                    sys.stdout.flush()
                    val = ''.join(buf).strip()
                    return val if val else None
                elif ch == b'\x1b':
                    # ESC or escape sequence → cancel
                    r2, _, _ = _select.select([fd], [], [], 0.05)
                    if r2:
                        os.read(fd, 1)  # consume '[' or similar
                        r3, _, _ = _select.select([fd], [], [], 0.05)
                        if r3:
                            os.read(fd, 1)  # consume final byte
                    sys.stdout.write('\n')
                    sys.stdout.flush()
                    return None
                elif ch in (b'\x7f', b'\x08'):  # Backspace
                    if buf:
                        buf.pop()
                        sys.stdout.write('\r\033[K' + f"{prompt}: " + ''.join(buf))
                        sys.stdout.flush()
                else:
                    char = ch.decode('utf-8', errors='ignore')
                    if char.isprintable():
                        buf.append(char)
                        sys.stdout.write(char)
                        sys.stdout.flush()
        finally:
            termios.tcsetattr(fd, termios.TCSADRAIN, old)

    def ask_goto_number(self, total: int) -> int | None:
        """번호로 이동: 1~total 범위의 순번을 입력받아 반환. ESC/빈 입력 시 None."""
        while True:
            raw = self.ask_path(f"Go to number (1-{total})")
            if raw is None:
                return None
            if raw.isdigit():
                n = int(raw)
                if 1 <= n <= total:
                    return n
            console.print(f"[red]Please enter a number between 1 and {total}.[/red]")

    def show_transcribe_prompt(self, buf: list[str], cursor_pos: int, init: bool = False) -> None:
        """받아쓰기 입력 프롬프트 표시.
        init=True: 힌트 줄 + 프롬프트 줄 새로 출력.
        init=False: 현재 프롬프트 줄만 덮어쓰기.
        cursor_pos: buf 내 커서 위치 (0 = 맨 앞).
        """
        typed = ''.join(buf)
        if init:
            sys.stdout.write(
                f"\n\033[2m{self._TRANSCRIBE_HINT}\033[0m\n"
                f"> {typed}"
            )
        else:
            sys.stdout.write(f"\r\033[K> {typed}")
        # 커서를 cursor_pos 위치로 이동 (끝이 아닌 경우)
        n = len(typed) - cursor_pos
        if n > 0:
            sys.stdout.write(f"\033[{n}D")
        sys.stdout.flush()

    def show_transcribe_result(self, answer: str, user_input: str) -> None:
        """사용자 입력 줄을 그 자리에서 컬러로 업데이트: 틀린 단어는 적색.

        Sequence alignment via DP so that omitted/inserted words don't cause
        all subsequent words to appear wrong.
        """
        sys.stdout.write(
            "\r\033[2K"           # clear current (prompt) line
            "\033[1A"             # move up to hint line
            "\r\033[2K"           # clear hint line
            f"\033[2m{self._TRANSCRIBE_HINT_RESULT}\033[0m{self._TRANSCRIBE_LEGEND}\n"
        )
        sys.stdout.flush()

        def _norm(w: str) -> str:
            return w.lower().strip(".,;:?!")

        answer_words = answer.split()
        input_words = user_input.split()
        n, m = len(answer_words), len(input_words)

        INF = n + m + 1
        dp = [[INF] * (m + 1) for _ in range(n + 1)]
        dp[0][0] = 0
        for i in range(1, n + 1):
            dp[i][0] = i
        for j in range(1, m + 1):
            dp[0][j] = j

        for i in range(1, n + 1):
            for j in range(1, m + 1):
                if _norm(answer_words[i - 1]) == _norm(input_words[j - 1]):
                    dp[i][j] = dp[i - 1][j - 1]
                else:
                    dp[i][j] = min(
                        dp[i - 1][j - 1] + 1,
                        dp[i - 1][j] + 1,
                        dp[i][j - 1] + 1,
                    )

        aligned: list[tuple[str, str]] = []
        i, j = n, m
        while i > 0 or j > 0:
            if i > 0 and j > 0 and _norm(answer_words[i - 1]) == _norm(input_words[j - 1]):
                aw, uw = answer_words[i - 1], input_words[j - 1]
                style = "bold green" if aw == uw else "bold yellow"
                aligned.append((uw, style))
                i -= 1; j -= 1
            elif i > 0 and j > 0 and dp[i][j] == dp[i - 1][j - 1] + 1:
                aligned.append((input_words[j - 1], "bold red"))
                i -= 1; j -= 1
            elif i > 0 and dp[i][j] == dp[i - 1][j] + 1:
                aligned.append(("_" * len(answer_words[i - 1]), "bold red"))
                i -= 1
            else:
                aligned.append((input_words[j - 1], "bold red"))
                j -= 1
        aligned.reverse()

        line = Text("> ")
        all_correct = all(s == "bold green" for _, s in aligned) and bool(aligned) and len(input_words) == n
        for k, (word, style) in enumerate(aligned):
            if k > 0:
                line.append(" ")
            line.append(word, style=style)
        if all_correct:
            line.append("  👍")
        console.print(line)

    def show_stats_header(self) -> None:
        """Stats screen header: program name + description + key bindings."""
        console.print(Panel(
            self._HEADER_TEXT + "\n\n" + self._HELP_TEXT_STATS,
            expand=False,
        ))

    def show_learning_stats(
        self,
        ranked: list[tuple[int, int]],
        sub_map: dict[int, Subtitle],
        total_seconds: float,
        page: int,
        progress_pct: float = 0.0,
        current_sub_index: int = -1,
        bookmarks: set[int] | None = None,
        cursor: int = -1,
    ) -> None:
        page_size = 10
        total = len(ranked)
        start = page * page_size
        end = min(start + page_size, total)
        entries = ranked[start:end]
        console.print(f"\n[bold cyan]── Learning Statistics ──[/bold cyan]  [dim]Progress: {progress_pct:.1f}%[/dim]\n")
        console.print(self._STATS_SEG_HEADER)
        for i, (idx, count) in enumerate(entries):
            abs_pos = start + i
            text = sub_map[idx].text if idx in sub_map else f"(subtitle {idx})"
            bm = "  [yellow]*[/yellow]  " if (bookmarks and idx in bookmarks) else "     "
            play = "  [bold yellow]▶[/bold yellow]  " if idx == current_sub_index else "     "
            if abs_pos == cursor:
                console.print(
                    "[bold]"
                    " [magenta]▶︎[/magenta] "
                    f"[cyan]{idx:>4}[/cyan]{bm}[green]{count:>3}[/green]{play}[white]{text}[/white]"
                    "[/bold]"
                )
            else:
                console.print(
                    f"   [dim]{idx:>4}{bm}[green]{count:>3}[/green][/dim]{play}[dim]{text}[/dim]"
                )
        hours, rem = divmod(int(total_seconds), 3600)
        minutes, seconds = divmod(rem, 60)
        time_str = f"{hours}h {minutes}m {seconds}s" if hours else f"{minutes}m {seconds}s"
        console.print(f"\n[dim]Total listening time: {time_str}  |  Page {page + 1}/{max(1, -(-total // page_size))}[/dim]")

    def show_date_stats(
        self,
        entries: list[tuple[str, dict[int, int]]],
        sub_map: dict[int, Subtitle],
        page: int,
        progress_pct: float = 0.0,
    ) -> None:
        from datetime import date as _date

        page_size = 10
        total = len(entries)
        start = page * page_size
        end = min(start + page_size, total)
        page_entries = entries[start:end]
        console.print(f"\n[bold cyan]── Date Statistics ──[/bold cyan]  [dim]Progress: {progress_pct:.1f}%[/dim]\n")

        def _day_seconds(sc: dict[int, int]) -> float:
            return sum(
                (sub_map[idx].end - sub_map[idx].start) * count
                for idx, count in sc.items()
                if idx in sub_map
            )

        all_seconds = [_day_seconds(sc) for _, sc in entries]
        max_seconds = max(all_seconds) if all_seconds else 1.0
        today_str = _date.today().strftime("%Y-%m-%d")

        console.print(self._STATS_DATE_HEADER)
        for date_str, sc in page_entries:
            subtitle_count = len(sc)
            repeat_count = sum(sc.values())
            total_seconds = _day_seconds(sc)
            hours, rem = divmod(int(total_seconds), 3600)
            minutes, seconds = divmod(rem, 60)
            time_str = f"{hours}h {minutes}m {seconds}s" if hours else f"{minutes}m {seconds}s"
            filled = round(total_seconds / max_seconds * 20) if max_seconds > 0 else 0
            bar = "█" * filled + "░" * (20 - filled)
            marker = "[yellow]▶[/yellow]" if date_str == today_str else " "
            console.print(f"{marker} [cyan]{date_str}[/cyan][white]  {subtitle_count:>6}   {repeat_count:>6}     {time_str:>11}  {bar}")
        page_count = max(1, -(-total // page_size))
        console.print(f"\n[dim]Page {page + 1}/{page_count}[/dim]")

    def show_bookmark_list(
        self,
        bookmark_indices: list[int],
        sub_map: dict[int, Subtitle],
        page: int,
        cursor: int,
        current_sub_index: int = -1,
        play_counts: dict[int, int] | None = None,
    ) -> None:
        """북마크 목록 화면: 10개씩 페이지, 커서 이동 가능."""
        page_size = 10
        total = len(bookmark_indices)
        start = page * page_size
        end = min(start + page_size, total)
        entries = bookmark_indices[start:end]
        page_count = max(1, -(-total // page_size))

        console.print(Panel(
            self._HEADER_TEXT + "\n\n" + self._HINT_BOOKMARK,
            expand=False,
        ))
        console.print(f"\n[bold cyan]── Bookmarks ──[/bold cyan]  [dim]({total} total)[/dim]\n")
        console.print(self._STATS_SEG_HEADER)
        bm = "  [yellow]*[/yellow]  "
        for i, sub_idx in enumerate(entries):
            abs_pos = start + i
            text = sub_map[sub_idx].text if sub_idx in sub_map else f"(subtitle {sub_idx})"
            count = (play_counts or {}).get(sub_idx, 0)
            play = "  [bold yellow]▶[/bold yellow]  " if sub_idx == current_sub_index else "     "
            if abs_pos == cursor:
                console.print(
                    "[bold]"
                    " [magenta]▶︎[/magenta] "
                    f"[cyan]{sub_idx:>4}[/cyan]{bm}[green]{count:>3}[/green]{play}[white]{text}[/white]"
                    "[/bold]"
                )
            else:
                console.print(f"   [dim]{sub_idx:>4}[/dim]{bm}[dim green]{count:>3}[/dim green]{play}[dim]{text}[/dim]")
        console.print(f"\n[dim]Page {page + 1}/{page_count}[/dim]")

    def show_stats(self, total_play: int, subtitle_index: int, subtitle_play: int) -> None:
        console.print(
            f"[dim]Total plays: {total_play}  |  Current segment: {subtitle_play}[/dim]"
        )
