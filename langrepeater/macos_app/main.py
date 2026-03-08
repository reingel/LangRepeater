"""Entry point: start the API server in a background thread, then launch the GUI."""

from __future__ import annotations

import threading
import time

import httpx
import uvicorn


def _run_server() -> None:
    uvicorn.run(
        "langrepeater.api.server:app",
        host="127.0.0.1",
        port=8000,
        log_level="warning",
        reload=False,
    )


def _wait_for_server(url: str, timeout: float = 10.0) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            httpx.get(url, timeout=0.5)
            return True
        except Exception:
            time.sleep(0.1)
    return False


def main() -> None:
    server_thread = threading.Thread(target=_run_server, daemon=True, name="api-server")
    server_thread.start()

    if not _wait_for_server("http://127.0.0.1:8000/docs"):
        print("Error: API server did not start in time.")
        return

    from langrepeater.macos_app.api_client import LangRepeaterClient
    from langrepeater.macos_app.app import LangRepeaterApp
    from langrepeater.macos_app.controller import AppController

    client = LangRepeaterClient()
    ctrl = AppController(client)

    # Offer to resume a previous session if any exist
    sessions = client.get_sessions()
    if sessions:
        import tkinter as tk
        from tkinter import simpledialog

        root = tk.Tk()
        root.withdraw()
        choices = "\n".join(
            f"{i + 1}. {sessions[i]['media_path']}" for i in range(len(sessions))
        )
        ans = simpledialog.askstring(
            "Resume session",
            f"Previous sessions found:\n{choices}\n\nEnter number to resume (or cancel for new file):",
        )
        root.destroy()
        if ans and ans.strip().isdigit():
            idx = int(ans.strip()) - 1
            if 0 <= idx < len(sessions):
                ctrl.resume_session(sessions[idx])

    app = LangRepeaterApp(ctrl)
    app.run()
    client.close()


if __name__ == "__main__":
    main()
