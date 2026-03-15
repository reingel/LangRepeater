from pathlib import Path

from rich.console import Console
from rich.panel import Panel
from rich.text import Text

from .core.models import Session, Subtitle

console = Console()


class RichUI:
    _HELP_TEXT = (
        "[dim]Space: play/pause  |  S: replay  |  D/→: next  |  A/←: prev  |  Q: quit[/dim]\n"
        "[dim]Z: start -0.1s  |  X: start +0.1s  |  ,: end -0.1s  |  .: end +0.1s[/dim]\n"
        "[dim]U: merge with next  |  I: split  |  V: show/hide subtitle[/dim]\n"
        "[dim]P: stats  |  ]: next page  |  [: prev page  |  ESC: home[/dim]"
    )

    def clear(self) -> None:
        console.clear()

    _HEADER_TEXT = (
        "[bold cyan]LangRepeater[/bold cyan]\n"
        "Audio segment repeater for language learning"
    )

    def show_welcome(self) -> None:
        """Home screen header: clear screen, then program name + description."""
        console.clear()
        console.print(Panel(self._HEADER_TEXT, expand=False))

    def show_study_header(self) -> None:
        """Study screen header: program name + description + key bindings."""
        console.print(Panel(
            self._HEADER_TEXT + "\n\n" + self._HELP_TEXT,
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
    def _mask_text(text: str) -> str:
        """Return text with middle words replaced by ___, keeping first and last word."""
        words = text.split()
        if len(words) <= 2:
            return text
        return words[0] + " " + " ".join("_" * len(w) for w in words[1:-1]) + " " + words[-1]

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

        console.print()
        for idx in indices:
            sub = subtitles[idx]
            display_text = self._mask_text(sub.text) if masked else sub.text
            if idx == current_index:
                ts = f"[{sub.start:.1f}s ~ {sub.end:.1f}s]"
                line = Text()
                line.append(f"{sub.index:>4}  ", style="dim")
                line.append(display_text, style="bold white")
                line.append(f"  {ts}", style="dim cyan")
                console.print(line)
            else:
                console.print(f"[dim]{sub.index:>4}  {display_text}[/dim]")

        # show progress info
        progress_pct = (current_index + 1) / n * 100
        console.print(
            f"\n[dim]Progress: {current_index + 1}/{n} ({progress_pct:.1f}%)[/dim]"
        )

    def show_home_menu(self, has_sessions: bool) -> str:
        """Show home menu. Returns: 'resume'|'new'|'url'|'delete'|'quit'."""
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
                return self.ask_path("Enter folder path")
            console.print("[red]Please enter 1 or 2.[/red]")

    def ask_split_point(self, subtitle) -> int | None:
        """Show split point candidates. Returns char position or None to cancel."""
        import re
        text = subtitle.text
        # Find candidate split positions
        positions: list[int] = []
        for m in re.finditer(r'\.\s+(?=\S)', text):  # mid-sentence period
            pos = m.end()
            if 0 < pos < len(text):
                positions.append(pos)
        for m in re.finditer(r',\s*', text):
            pos = m.end()
            if 0 < pos < len(text) and pos not in positions:
                positions.append(pos)
        for m in re.finditer(r'\b(and|or)\b', text, re.IGNORECASE):
            pos = m.start()
            if 0 < pos < len(text) and pos not in positions:
                positions.append(pos)
        for m in re.finditer(r';\s*', text):
            pos = m.end()
            if 0 < pos < len(text) and pos not in positions:
                positions.append(pos)
        # Japanese punctuation: 。！？、（split after）; 「」 splits before 「
        for m in re.finditer(r'[。！？]\s*', text):
            pos = m.end()
            if 0 < pos < len(text) and pos not in positions:
                positions.append(pos)
        for m in re.finditer(r'、\s*', text):
            pos = m.end()
            if 0 < pos < len(text) and pos not in positions:
                positions.append(pos)
        positions = sorted(set(positions))
        if not positions:
            console.print("[yellow]No split points found.[/yellow]")
            return None
        console.print("\n[bold]Select split point:[/bold]")
        for i, pos in enumerate(positions, 1):
            before = text[:pos].rstrip()
            after = text[pos:].lstrip()
            console.print(f"  [cyan]{i}[/cyan]. {before} [bold red]|[/bold red] {after}")
        while True:
            raw = console.input(f"\nEnter number (1-{len(positions)}) or C to cancel: ").strip()
            if raw.lower() == "c":
                return None
            if raw.isdigit():
                n = int(raw)
                if 1 <= n <= len(positions):
                    return positions[n - 1]
            console.print("[red]Please enter a valid number.[/red]")

    def show_message(self, msg: str) -> None:
        console.print(msg)

    def ask_path(self, prompt: str) -> str | None:
        val = console.input(f"{prompt} (or C to cancel): ").strip()
        return None if val.lower() == "c" else val

    def show_learning_stats(
        self,
        ranked: list[tuple[int, int]],
        sub_map: dict[int, Subtitle],
        total_seconds: float,
        page: int,
    ) -> None:
        page_size = 10
        total = len(ranked)
        start = page * page_size
        end = min(start + page_size, total)
        entries = ranked[start:end]
        console.print("\n[bold cyan]── Learning Statistics ──[/bold cyan]")
        for rank, (idx, count) in enumerate(entries, start + 1):
            text = sub_map[idx].text if idx in sub_map else f"(subtitle {idx})"
            console.print(f"  [cyan]{rank:>2}[/cyan]. [bold]{count}x[/bold]  [dim]#{idx}[/dim]  {text}")
        hours, rem = divmod(int(total_seconds), 3600)
        minutes, seconds = divmod(rem, 60)
        time_str = f"{hours}h {minutes}m {seconds}s" if hours else f"{minutes}m {seconds}s"
        console.print(f"\n[dim]Total listening time: {time_str}  |  Page {page + 1}/{max(1, -(-total // page_size))}[/dim]")

    def show_stats(self, total_play: int, subtitle_index: int, subtitle_play: int) -> None:
        console.print(
            f"[dim]Total plays: {total_play}  |  Current segment: {subtitle_play}[/dim]"
        )
