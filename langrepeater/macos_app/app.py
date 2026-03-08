"""tkinter-based macOS GUI for LangRepeater."""

from __future__ import annotations

import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from langrepeater.macos_app.controller import AppController


class LangRepeaterApp:
    """Main window for the LangRepeater macOS app."""

    # Fonts
    _FONT_NORMAL = ("Helvetica Neue", 14)
    _FONT_BOLD = ("Helvetica Neue", 14, "bold")
    _FONT_SMALL = ("Helvetica Neue", 11)
    _FONT_TITLE = ("Helvetica Neue", 18, "bold")

    def __init__(self, controller: AppController) -> None:
        self.ctrl = controller
        self.root = tk.Tk()
        self._build_window()
        self._bind_keys()

    # ------------------------------------------------------------------
    # Window construction
    # ------------------------------------------------------------------

    def _build_window(self) -> None:
        root = self.root
        root.title("LangRepeater")
        root.geometry("640x520")
        root.resizable(True, True)
        root.configure(bg="#1e1e1e")
        root.protocol("WM_DELETE_WINDOW", self._on_quit)

        # ── Title bar ────────────────────────────────────────────────
        title_frame = tk.Frame(root, bg="#1e1e1e", pady=12)
        title_frame.pack(fill="x", padx=20)
        tk.Label(
            title_frame, text="LangRepeater", font=self._FONT_TITLE,
            fg="#f0f0f0", bg="#1e1e1e",
        ).pack(side="left")
        open_btn = tk.Label(
            title_frame, text="Open Files",
            font=self._FONT_SMALL, fg="#f0f0f0", bg="#3a3a3a",
            padx=10, pady=4, cursor="hand2",
        )
        open_btn.bind("<Button-1>", lambda _: self._on_open_files())
        open_btn.bind("<Enter>", lambda _: open_btn.config(bg="#555555"))
        open_btn.bind("<Leave>", lambda _: open_btn.config(bg="#3a3a3a"))
        open_btn.pack(side="right")

        # ── File info ─────────────────────────────────────────────────
        info_frame = tk.Frame(root, bg="#2a2a2a", pady=8)
        info_frame.pack(fill="x", padx=20, pady=(0, 10))
        self._file_var = tk.StringVar(value="No file loaded")
        self._progress_var = tk.StringVar(value="")
        tk.Label(
            info_frame, textvariable=self._file_var,
            font=self._FONT_SMALL, fg="#aaaaaa", bg="#2a2a2a", padx=12,
        ).pack(side="left")
        tk.Label(
            info_frame, textvariable=self._progress_var,
            font=self._FONT_SMALL, fg="#888888", bg="#2a2a2a", padx=12,
        ).pack(side="right")

        # ── Subtitles ─────────────────────────────────────────────────
        sub_outer = tk.Frame(root, bg="#1e1e1e")
        sub_outer.pack(fill="both", expand=True, padx=20)

        self._prev_var = tk.StringVar()
        self._curr_var = tk.StringVar()
        self._next_var = tk.StringVar()

        tk.Label(
            sub_outer, textvariable=self._prev_var,
            font=self._FONT_NORMAL, fg="#555555", bg="#1e1e1e",
            wraplength=580, justify="center",
        ).pack(pady=(16, 8))

        curr_frame = tk.Frame(sub_outer, bg="#2c2c2c", pady=14, padx=16)
        curr_frame.pack(fill="x")
        tk.Label(
            curr_frame, textvariable=self._curr_var,
            font=self._FONT_BOLD, fg="#ffffff", bg="#2c2c2c",
            wraplength=560, justify="center",
        ).pack()

        tk.Label(
            sub_outer, textvariable=self._next_var,
            font=self._FONT_NORMAL, fg="#555555", bg="#1e1e1e",
            wraplength=580, justify="center",
        ).pack(pady=(8, 16))

        # ── Stats bar ─────────────────────────────────────────────────
        stats_frame = tk.Frame(root, bg="#252525", pady=6)
        stats_frame.pack(fill="x", padx=20, pady=(0, 10))
        self._stats_var = tk.StringVar()
        tk.Label(
            stats_frame, textvariable=self._stats_var,
            font=self._FONT_SMALL, fg="#777777", bg="#252525", padx=12,
        ).pack(side="left")

        # ── Controls ──────────────────────────────────────────────────
        # Use Label instead of Button: macOS dark mode ignores Button fg/bg.
        ctrl_frame = tk.Frame(root, bg="#1e1e1e", pady=12)
        ctrl_frame.pack()
        self._make_button(ctrl_frame, "◀ Prev", self._on_prev).pack(side="left", padx=6)
        self._make_button(ctrl_frame, "▶ Play", self._on_play).pack(side="left", padx=6)
        self._make_button(ctrl_frame, "Next ▶", self._on_next).pack(side="left", padx=6)

        # ── Hint ──────────────────────────────────────────────────────
        hint = "Space/S: Play  |  D/→: Next  |  A/←: Prev  |  Q/Esc: Quit"
        tk.Label(
            root, text=hint, font=self._FONT_SMALL, fg="#444444", bg="#1e1e1e",
        ).pack(pady=(0, 10))

    def _make_button(self, parent: tk.Frame, text: str, command) -> tk.Label:
        """Return a Label styled as a button; works in macOS dark mode."""
        lbl = tk.Label(
            parent, text=text,
            font=self._FONT_NORMAL, fg="#f0f0f0", bg="#3a3a3a",
            padx=18, pady=8, cursor="hand2",
        )
        lbl.bind("<Button-1>", lambda _: command())
        lbl.bind("<Enter>", lambda _: lbl.config(bg="#555555"))
        lbl.bind("<Leave>", lambda _: lbl.config(bg="#3a3a3a"))
        return lbl

    def _bind_keys(self) -> None:
        r = self.root
        r.bind("<space>", lambda _: self._on_play())
        r.bind("s", lambda _: self._on_play())
        r.bind("S", lambda _: self._on_play())
        r.bind("<Right>", lambda _: self._on_next())
        r.bind("d", lambda _: self._on_next())
        r.bind("D", lambda _: self._on_next())
        r.bind("<Left>", lambda _: self._on_prev())
        r.bind("a", lambda _: self._on_prev())
        r.bind("A", lambda _: self._on_prev())
        r.bind("q", lambda _: self._on_quit())
        r.bind("Q", lambda _: self._on_quit())
        r.bind("<Escape>", lambda _: self._on_quit())

    # ------------------------------------------------------------------
    # Actions
    # ------------------------------------------------------------------

    def _on_open_files(self) -> None:
        media = filedialog.askopenfilename(
            title="Select media file",
            filetypes=[("Audio/Video", "*.mp3 *.mp4"), ("All files", "*.*")],
        )
        if not media:
            return
        srt = filedialog.askopenfilename(
            title="Select subtitle file",
            filetypes=[("SubRip", "*.srt"), ("All files", "*.*")],
        )
        if not srt:
            return
        try:
            self.ctrl.load_files(media, srt)
        except Exception as exc:
            messagebox.showerror("Error", str(exc))
            return
        self._refresh()

    def _on_play(self) -> None:
        try:
            self.ctrl.play_current()
        except Exception as exc:
            messagebox.showerror("Playback error", str(exc))
        self._refresh_stats()

    def _on_next(self) -> None:
        if self.ctrl.go_next():
            try:
                self.ctrl.play_current()
            except Exception as exc:
                messagebox.showerror("Playback error", str(exc))
        self._refresh()

    def _on_prev(self) -> None:
        if self.ctrl.go_prev():
            try:
                self.ctrl.play_current()
            except Exception as exc:
                messagebox.showerror("Playback error", str(exc))
        self._refresh()

    def _on_quit(self) -> None:
        self.ctrl.save_progress()
        self.ctrl.stop()
        self.root.destroy()

    # ------------------------------------------------------------------
    # Display refresh
    # ------------------------------------------------------------------

    def _refresh(self) -> None:
        state = self.ctrl.state
        if state.media_path:
            self._file_var.set(Path(state.media_path).name)
            self._progress_var.set(self.ctrl.progress_text())

        prev, curr, nxt = self.ctrl.display_window()
        self._prev_var.set(prev["text"] if prev else "")
        self._curr_var.set(curr["text"] if curr else "— no file loaded —")
        self._next_var.set(nxt["text"] if nxt else "")
        self._refresh_stats()

    def _refresh_stats(self) -> None:
        mp = self.ctrl.state.media_path
        if not mp:
            return
        try:
            stats = self.ctrl.client.get_stats(mp)
            sub = self.ctrl.current_subtitle()
            sub_count = 0
            if sub:
                sub_count = stats["subtitle_play_counts"].get(str(sub["index"]), 0)
            self._stats_var.set(
                f"Segment plays: {sub_count}  |  Total plays: {stats['total_play_count']}"
            )
        except Exception:
            pass

    # ------------------------------------------------------------------

    def run(self) -> None:
        self._refresh()
        self.root.mainloop()

    # Expose root for testing without mainloop
    @property
    def root_widget(self) -> tk.Tk:
        return self.root
