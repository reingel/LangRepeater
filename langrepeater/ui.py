from pathlib import Path

from rich.console import Console
from rich.panel import Panel
from rich.text import Text

from .core.models import Session, Subtitle

console = Console()


class RichUI:
    def show_welcome(self) -> None:
        console.print(Panel(
            "[bold cyan]LangRepeater[/bold cyan]\n"
            "Audio segment repeater for language learning\n\n"
            "[dim]Space/S: play  |  D/→: next  |  A/←: prev  |  Q: quit  |  ESC/H: home[/dim]\n"
            "[dim]Z: start -0.1s  |  X: start +0.1s  |  N: end -0.1s  |  M: end +0.1s[/dim]\n"
            "[dim]P: learning stats[/dim]",
            expand=False,
        ))

    def show_file_list(self, files: list[str], prompt: str) -> int | None:
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

    def show_subtitles(self, subtitles: list[Subtitle], current_index: int) -> None:
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
            if idx == current_index:
                ts = f"[{sub.start:.1f}s ~ {sub.end:.1f}s]"
                line = Text()
                line.append(f"{sub.index:>4}  ", style="dim")
                line.append(sub.text, style="bold white")
                line.append(f"  {ts}", style="dim cyan")
                console.print(line)
            else:
                console.print(f"[dim]{sub.index:>4}  {sub.text}[/dim]")

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
        console.print(f"  [cyan]{n}[/cyan]. Open new file")
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
        console.print("\n[bold]Select session to resume:[/bold]")
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

    def ask_delete_session(self, sessions: list[Session]) -> int | None:
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
        name = Path(session.media_path).name
        raw = console.input(f"\nDelete [bold]{name}[/bold]? (y/N): ").strip().lower()
        return raw == "y"

    def ask_folder(self, previous_dir: str) -> str | None:
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

    def show_message(self, msg: str) -> None:
        console.print(msg)

    def ask_path(self, prompt: str) -> str:
        return console.input(f"{prompt}: ").strip()

    def show_learning_stats(
        self,
        top10: list[tuple[int, int]],
        sub_map: dict[int, Subtitle],
        total_seconds: float,
    ) -> None:
        console.print("\n[bold cyan]── Learning Statistics ──[/bold cyan]")
        for rank, (idx, count) in enumerate(top10, 1):
            text = sub_map[idx].text if idx in sub_map else f"(subtitle {idx})"
            console.print(f"  [cyan]{rank:>2}[/cyan]. [bold]{count}x[/bold]  {text}")
        hours, rem = divmod(int(total_seconds), 3600)
        minutes, seconds = divmod(rem, 60)
        if hours:
            time_str = f"{hours}h {minutes}m {seconds}s"
        else:
            time_str = f"{minutes}m {seconds}s"
        console.print(f"\n[dim]Total listening time: {time_str}[/dim]")

    def show_stats(self, total_play: int, subtitle_index: int, subtitle_play: int) -> None:
        console.print(
            f"[dim]Total plays: {total_play}  |  Current segment: {subtitle_play}[/dim]"
        )
