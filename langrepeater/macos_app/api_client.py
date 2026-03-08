"""HTTP client for the LangRepeater REST API."""

from __future__ import annotations

import httpx


class LangRepeaterClient:
    """Thin wrapper around the LangRepeater FastAPI endpoints."""

    def __init__(self, base_url: str = "http://127.0.0.1:8000") -> None:
        self._http = httpx.Client(base_url=base_url, timeout=5.0)

    # ------------------------------------------------------------------
    # Files
    # ------------------------------------------------------------------

    def find_media(self, directory: str) -> list[str]:
        resp = self._http.get("/files/media", params={"directory": directory})
        resp.raise_for_status()
        return resp.json()

    def find_srt(self, directory: str) -> list[str]:
        resp = self._http.get("/files/srt", params={"directory": directory})
        resp.raise_for_status()
        return resp.json()

    # ------------------------------------------------------------------
    # Subtitles
    # ------------------------------------------------------------------

    def get_subtitles(self, srt_path: str) -> list[dict]:
        resp = self._http.get("/subtitles/", params={"srt_path": srt_path})
        resp.raise_for_status()
        return resp.json()

    # ------------------------------------------------------------------
    # Audio
    # ------------------------------------------------------------------

    def play(self, media_path: str, start: float, end: float) -> None:
        resp = self._http.post("/audio/play", json={
            "media_path": media_path,
            "start": start,
            "end": end,
        })
        resp.raise_for_status()

    def stop(self) -> None:
        resp = self._http.post("/audio/stop")
        resp.raise_for_status()

    # ------------------------------------------------------------------
    # Sessions
    # ------------------------------------------------------------------

    def get_sessions(self) -> list[dict]:
        resp = self._http.get("/sessions/")
        resp.raise_for_status()
        return resp.json()

    def upsert_session(self, media_path: str, srt_path: str, current_index: int) -> None:
        resp = self._http.post("/sessions/", json={
            "media_path": media_path,
            "srt_path": srt_path,
            "current_index": current_index,
        })
        resp.raise_for_status()

    def delete_session(self, media_path: str) -> None:
        resp = self._http.request("DELETE", "/sessions/", json={"media_path": media_path})
        resp.raise_for_status()

    # ------------------------------------------------------------------
    # Stats
    # ------------------------------------------------------------------

    def get_stats(self, media_path: str) -> dict:
        resp = self._http.get("/stats/", params={"media_path": media_path})
        resp.raise_for_status()
        return resp.json()

    def increment_play(self, media_path: str, subtitle_index: int) -> None:
        resp = self._http.post("/stats/increment", json={
            "media_path": media_path,
            "subtitle_index": subtitle_index,
        })
        resp.raise_for_status()

    # ------------------------------------------------------------------

    def close(self) -> None:
        self._http.close()
