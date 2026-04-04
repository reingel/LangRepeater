import sys
from pathlib import Path

from rich.console import Console
from rich.panel import Panel
from rich.text import Text

from .core.models import Session, Subtitle

console = Console()


class RichUI:
    _HELP_TEXT_L = (
        "[dim]Space: play/pause      |  A/←/↑: prev         |  D/→/↓: next   |  [: prev 3  |  ]: next 3[/dim]\n"
        "[dim]V: show/hide subtitle  |  G: goto             |  Q: quit       |  ESC: home[/dim]"
    )
    _HELP_TEXT_LR = (
        "[dim]Space: play/pause      |  A/←/↑: prev         |  D/→/↓: next   |  [: prev 3  |  ]: next 3[/dim]\n"
        "[dim]V: show/hide subtitle  |  G: goto             |  Q: quit       |  ESC: home[/dim]\n"
        "[dim]S: replay              |  U: merge with next  |  I: split      |  T: transcribe[/dim]\n"
        "[dim]Z: start -0.1s         |  X: start +0.1s      |  ,: end -0.1s  |  .: end +0.1s[/dim]\n"
        "[dim]P: segment stats       |  0: date stats[/dim]"
    )
    _HELP_TEXT_STATS = (
        "[dim][: prev page  |  ]: next page  |  any key: back[/dim]"
    )

    _HEADER_TEXT = (
        "[bold cyan]LangRepeater[/bold cyan]\n"
        "Audio segment repeater for language learning"
    )

    _VISIBLE_PUNCT = frozenset(".,;:?!-")

    def clear(self) -> None:
        console.clear()

    def show_welcome(self) -> None:
        """Home screen header: clear screen, then program name + description."""
        console.clear()
        console.print(Panel(self._HEADER_TEXT, expand=False))

    def show_study_header(self, mode: str = "LR") -> None:
        """Study screen header: program name + description + mode + key bindings."""
        if mode == "L":
            mode_line = (
                "[bold white]1: Listening mode[/bold white]  |  "
                "[dim]2: Listen & Repeat mode[/dim]"
            )
            help_text = self._HELP_TEXT_L
        else:
            mode_line = (
                "[dim]1: Listening mode[/dim]  |  "
                "[bold white]2: Listen & Repeat mode[/bold white]"
            )
            help_text = self._HELP_TEXT_LR
        console.print(Panel(
            self._HEADER_TEXT + "\n\n" + mode_line + "\n\n" + help_text,
            expand=False,
        ))

    def show_file_list(self, files: list[str], prompt: str) -> int | None:
        self.show_welcome()
        console.print(f"\n[bold]{prompt}[/bold]")
        for i, f in enumerate(files, 1):
            console.print(f"  [cyan]{i}[/cyan]. {Path(f).name}")
        while True:
            raw = console.input(f"\nEnter number (1-{len(files)}) or C to cancel: ").strip()
            if raw.lower() == "c":
                return None
            if raw.isdigit():
                n = int(raw)
                if 1 <= n <= len(files):
                    return n - 1
            console.print("[red]Please enter a valid number.[/red]")

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

    def show_subtitles(self, subtitles: list[Subtitle], current_index: int, masked: bool = True) -> None:
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
        progress_pct = (current_index + 1) / n * 100
        filled = round(progress_pct / 100 * total_num_blocks)
        bar = "█" * filled + "░" * (total_num_blocks - filled)
        console.print(
            f"\n [dim]Progress: {current_index + 1}/{n} ({progress_pct:.1f}%)  {bar}[/dim]"
        )

        console.print()
        for idx in indices:
            sub = subtitles[idx]
            display_text = self._mask_text(sub.text) if masked else sub.text
            if idx == current_index:
                ts = f"[{sub.start:.2f}s ~ {sub.end:.2f}s]"
                line = Text()
                line.append(f"{sub.index:>4}  ", style="dim bold cyan")
                line.append(display_text, style="bold white")
                line.append(f"  {ts}", style="dim bold cyan")
                console.print(line)
            else:
                console.print(f"[dim white]{sub.index:>4}  {display_text}[/dim white]")

    def show_home_menu(self, has_sessions: bool) -> str:
        """Show home menu. Returns: 'resume'|'new'|'url'|'url:<url>'|'delete'|'quit'."""
        console.print()
        n = 1
        if has_sessions:
            console.print(f"  [cyan]{n}[/cyan]. Continue previous session")
            n += 1
        console.print(f"  [cyan]{n}[/cyan]. Open a new file")
        n += 1
        console.print(f"  [cyan]{n}[/cyan]. Enter URL")
        n += 1
        if has_sessions:
            console.print(f"  [cyan]{n}[/cyan]. Delete a session")
            n += 1
        total = n - 1
        console.print(f"\n  [dim]Q: Quit[/dim]")
        while True:
            raw = console.input(f"\nEnter number (1-{total}) or Q to quit: ").strip()
            if raw.lower() == "q":
                return "quit"
            if raw.startswith(("http://", "https://")):
                return f"url:{raw}"
            if raw.isdigit():
                val = int(raw)
                idx = 1
                if has_sessions:
                    if val == idx:
                        return "resume"
                    idx += 1
                if val == idx:
                    return "new"
                idx += 1
                if val == idx:
                    return "url"
                idx += 1
                if has_sessions and val == idx:
                    return "delete"
            console.print("[red]Please enter a valid number.[/red]")

    def ask_resume_session(self, sessions: list[Session]) -> int | None:
        """Show session list for resuming. Returns index or None to cancel."""
        self.show_welcome()
        console.print("\n[bold]Select session to resume:[/bold]")
        for i, s in enumerate(sessions, 1):
            marker = "[yellow]▶[/yellow] " if i == 1 else "  "
            console.print(
                f"{marker}[cyan]{i}[/cyan]. {Path(s.media_path).name}  "
                f"[dim](segment {s.current_index + 1})[/dim]"
            )
        while True:
            raw = console.input(f"\nEnter number (1-{len(sessions)}) or C to cancel: ").strip()
            if raw == "":
                return 0
            if raw.lower() == "c":
                return None
            if raw.isdigit():
                n = int(raw)
                if 1 <= n <= len(sessions):
                    return n - 1
            console.print("[red]Please enter a valid number.[/red]")

    def ask_delete_session(self, sessions: list[Session]) -> int | None:
        self.show_welcome()
        console.print("\n[bold]Select session to delete:[/bold]")
        for i, s in enumerate(sessions, 1):
            console.print(
                f"  [cyan]{i}[/cyan]. {Path(s.media_path).name}  "
                f"[dim](segment {s.current_index + 1})[/dim]"
            )
        while True:
            raw = console.input(f"\nEnter number (1-{len(sessions)}) or C to cancel: ").strip()
            if raw.lower() == "c":
                return None
            if raw.isdigit():
                n = int(raw)
                if 1 <= n <= len(sessions):
                    return n - 1
            console.print("[red]Please enter a valid number.[/red]")

    def confirm_delete(self, session: Session) -> bool:
        self.show_welcome()
        name = Path(session.media_path).name
        raw = console.input(f"\nDelete [bold]{name}[/bold]? (y/N): ").strip().lower()
        return raw == "y"

    @staticmethod
    def _open_file_dialog(initial_dir: str = "~") -> str | None:
        """Open native macOS file picker dialog for mp3/mp4 files via osascript."""
        import os
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
        self.show_welcome()
        console.print("\n[bold]Select folder:[/bold]")
        console.print(f"  [cyan]1[/cyan]. Same folder: [dim]{previous_dir}[/dim]")
        console.print(f"  [cyan]2[/cyan]. Different folder")
        while True:
            raw = console.input("\nEnter number (1-2) or C to cancel: ").strip()
            if raw.lower() == "c":
                return None
            if raw == "1":
                return previous_dir
            if raw == "2":
                console.print("[dim]Opening file dialog...[/dim]")
                path = self._open_file_dialog(previous_dir)
                if path is None:
                    console.print("[yellow]Dialog cancelled.[/yellow]")
                    continue
                return path
            console.print("[red]Please enter 1 or 2.[/red]")

    def ask_split_point(self, subtitle, fd: int) -> int | None:
        """Show split point candidates. Returns char position or None to cancel."""
        import os
        import re
        text = subtitle.text
        # Find candidate split positions
        positions: list[int] = []
        # English: after . , ; :
        for punct_pattern in (r'\.\s*', r',\s*', r';\s*', r':\s*'):
            for m in re.finditer(punct_pattern, text):
                pos = m.end()
                if 0 < pos < len(text) and pos not in positions:
                    positions.append(pos)
        # English: before and/or
        for m in re.finditer(r'\b(and|or|but)\b', text, re.IGNORECASE):
            pos = m.start()
            if 0 < pos < len(text) and pos not in positions:
                positions.append(pos)
        # English: before clause words
        for m in re.finditer(r'\b(when|what|where|which|that|because|due to|however|until|if|so)\b', text, re.IGNORECASE):
            pos = m.start()
            if 0 < pos < len(text) and pos not in positions:
                positions.append(pos)
        # Japanese: after 。！？、
        for m in re.finditer(r'[。！？、]\s*', text):
            pos = m.end()
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
            sys.stdout.write(f"\n\033[2m      {bar}\033[0m\n")
        else:
            sys.stdout.write(f"\n      {bar}\n")
        sys.stdout.flush()

    def update_animation_line(self, progress: float, dim: bool = False) -> None:
        """Overwrite animation bar in-place (cursor must be on the line after the bar)."""
        bar = self._make_animation_bar(progress)
        if dim:
            sys.stdout.write(f"\033[1A\r\033[2K\033[2m      {bar}\033[0m\n")
        else:
            sys.stdout.write(f"\033[1A\r\033[2K      {bar}\n")
        sys.stdout.flush()

    def show_message(self, msg: str) -> None:
        console.print(msg)

    def ask_path(self, prompt: str) -> str | None:
        val = console.input(f"{prompt} (or C to cancel): ").strip()
        return None if val.lower() == "c" else val

    def ask_goto_number(self, total: int) -> int | None:
        """번호로 이동: 1~total 범위의 순번을 입력받아 반환. 취소 시 None."""
        while True:
            raw = console.input(f"Go to number (1-{total}, or C to cancel): ").strip()
            if raw.lower() == "c":
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
                "\n\033[2mTranscribe [Tab: play | Opt+V: show/hide subtitle | ESC/Enter: return]\033[0m\n"
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
        sys.stdout.write("\r\033[2K")
        sys.stdout.flush()

        def _norm(w: str) -> str:
            return w.lower().strip(".,;:?!")

        answer_words = answer.split()
        input_words = user_input.split()
        n, m = len(answer_words), len(input_words)

        # DP: edit distance keeping track of operations
        # dp[i][j] = min cost to align answer[:i] with input[:j]
        # cost: match=0, substitute=1, delete(skip answer word)=1, insert(extra input word)=1
        INF = n + m + 1
        dp = [[INF] * (m + 1) for _ in range(n + 1)]
        dp[0][0] = 0
        for i in range(1, n + 1):
            dp[i][0] = i  # delete answer words
        for j in range(1, m + 1):
            dp[0][j] = j  # insert input words

        for i in range(1, n + 1):
            for j in range(1, m + 1):
                if _norm(answer_words[i - 1]) == _norm(input_words[j - 1]):
                    dp[i][j] = dp[i - 1][j - 1]          # match
                else:
                    dp[i][j] = min(
                        dp[i - 1][j - 1] + 1,  # substitute
                        dp[i - 1][j] + 1,       # delete (skip answer word)
                        dp[i][j - 1] + 1,       # insert (extra input word)
                    )

        # Backtrace to get alignment
        # Each element: (input_word_or_None, is_correct)
        aligned: list[tuple[str, bool]] = []
        i, j = n, m
        while i > 0 or j > 0:
            if i > 0 and j > 0 and _norm(answer_words[i - 1]) == _norm(input_words[j - 1]):
                aligned.append((input_words[j - 1], True))
                i -= 1; j -= 1
            elif i > 0 and j > 0 and dp[i][j] == dp[i - 1][j - 1] + 1:
                aligned.append((input_words[j - 1], False))  # substitution
                i -= 1; j -= 1
            elif i > 0 and dp[i][j] == dp[i - 1][j] + 1:
                aligned.append(("_" * len(answer_words[i - 1]), False))  # omitted word
                i -= 1
            else:
                aligned.append((input_words[j - 1], False))  # extra input word
                j -= 1
        aligned.reverse()

        line = Text("> ")
        all_correct = all(ok for _, ok in aligned) and bool(aligned) and len(input_words) == n
        for k, (word, ok) in enumerate(aligned):
            if k > 0:
                line.append(" ")
            line.append(word, style="bold green" if ok else "bold red")
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
    ) -> None:
        page_size = 10
        total = len(ranked)
        start = page * page_size
        end = min(start + page_size, total)
        entries = ranked[start:end]
        console.print(f"\n[bold cyan]── Learning Statistics ──[/bold cyan]  [dim]Progress: {progress_pct:.1f}%[/dim]\n")
        console.print(f"[bold white]     # repeats  sentence[/bold white]")
        for idx, count in entries:
            text = sub_map[idx].text if idx in sub_map else f"(subtitle {idx})"
            marker = "[yellow]▶[/yellow]" if idx == current_sub_index else " "
            console.print(f"{marker} [white dim]{idx:>4}[/white dim]  [bold cyan]{count:>4}x[/bold cyan]   [bold white]{text}[/bold white]")
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
        page_size = 10
        total = len(entries)
        start = page * page_size
        end = min(start + page_size, total)
        page_entries = entries[start:end]
        console.print(f"\n[bold cyan]── Date Statistics ──[/bold cyan]  [dim]Progress: {progress_pct:.1f}%[/dim]\n")
        # pre-compute seconds for all entries (for relative bar scaling)
        def _day_seconds(sc: dict[int, int]) -> float:
            return sum(
                (sub_map[idx].end - sub_map[idx].start) * count
                for idx, count in sc.items()
                if idx in sub_map
            )

        all_seconds = [_day_seconds(sc) for _, sc in entries]
        max_seconds = max(all_seconds) if all_seconds else 1.0

        from datetime import date as _date
        today_str = _date.today().strftime("%Y-%m-%d")
        console.print(f"[bold white]               segments  repeats   net play time[/bold white]")
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

    def show_stats(self, total_play: int, subtitle_index: int, subtitle_play: int) -> None:
        console.print(
            f"[dim]Total plays: {total_play}  |  Current segment: {subtitle_play}[/dim]"
        )
