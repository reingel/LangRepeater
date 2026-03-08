"""Tests for the LangRepeater FastAPI server (Phase 2)."""

import textwrap
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from langrepeater.api.server import create_app

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def client():
    app = create_app()
    return TestClient(app)


@pytest.fixture()
def tmp_srt(tmp_path: Path) -> Path:
    srt_content = textwrap.dedent("""\
        1
        00:00:01,000 --> 00:00:03,000
        Hello world

        2
        00:00:04,000 --> 00:00:06,000
        How are you?

    """)
    f = tmp_path / "test.srt"
    f.write_text(srt_content, encoding="utf-8")
    return f


@pytest.fixture()
def tmp_media(tmp_path: Path) -> Path:
    f = tmp_path / "audio.mp3"
    f.write_bytes(b"")  # dummy file – not actually played
    return f


@pytest.fixture()
def progress_store(tmp_path: Path):
    """Patch ProgressStore to use a temp file."""
    from langrepeater.core.progress_store import ProgressStore
    store = ProgressStore(str(tmp_path / "progress.yaml"))
    with patch("langrepeater.api.routers.sessions._store", store):
        yield store


@pytest.fixture()
def stats_store(tmp_path: Path):
    """Patch StatsStore to use a temp file."""
    from langrepeater.core.stats_store import StatsStore
    store = StatsStore(str(tmp_path / "stat.yaml"))
    with patch("langrepeater.api.routers.stats._store", store):
        yield store


# ---------------------------------------------------------------------------
# /files
# ---------------------------------------------------------------------------


class TestFilesRoutes:
    def test_search_media_returns_files(self, client, tmp_path):
        (tmp_path / "a.mp3").touch()
        (tmp_path / "b.mp4").touch()
        (tmp_path / "ignore.txt").touch()

        resp = client.get("/files/media", params={"directory": str(tmp_path)})
        assert resp.status_code == 200
        paths = resp.json()
        assert len(paths) == 2
        assert all(p.endswith((".mp3", ".mp4")) for p in paths)

    def test_search_media_empty_dir(self, client, tmp_path):
        resp = client.get("/files/media", params={"directory": str(tmp_path)})
        assert resp.status_code == 200
        assert resp.json() == []

    def test_search_media_nonexistent_dir(self, client):
        resp = client.get("/files/media", params={"directory": "/nonexistent/path"})
        assert resp.status_code == 200
        assert resp.json() == []

    def test_search_srt_returns_files(self, client, tmp_path):
        (tmp_path / "sub.srt").touch()
        resp = client.get("/files/srt", params={"directory": str(tmp_path)})
        assert resp.status_code == 200
        paths = resp.json()
        assert len(paths) == 1
        assert paths[0].endswith(".srt")

    def test_search_srt_empty(self, client, tmp_path):
        resp = client.get("/files/srt", params={"directory": str(tmp_path)})
        assert resp.status_code == 200
        assert resp.json() == []


# ---------------------------------------------------------------------------
# /subtitles
# ---------------------------------------------------------------------------


class TestSubtitlesRoutes:
    def test_get_subtitles_ok(self, client, tmp_srt):
        resp = client.get("/subtitles/", params={"srt_path": str(tmp_srt)})
        assert resp.status_code == 200
        subs = resp.json()
        assert len(subs) == 2
        assert subs[0]["index"] == 1
        assert subs[0]["start"] == pytest.approx(1.0)
        assert subs[0]["end"] == pytest.approx(3.0)
        assert subs[0]["text"] == "Hello world"
        assert subs[1]["index"] == 2
        assert subs[1]["text"] == "How are you?"

    def test_get_subtitles_not_found(self, client):
        resp = client.get("/subtitles/", params={"srt_path": "/no/such/file.srt"})
        assert resp.status_code == 404

    def test_get_subtitles_missing_param(self, client):
        resp = client.get("/subtitles/")
        assert resp.status_code == 422  # FastAPI validation error


# ---------------------------------------------------------------------------
# /audio
# ---------------------------------------------------------------------------


class TestAudioRoutes:
    def _mock_player(self):
        mock = MagicMock()
        return mock

    def test_play_audio(self, client, tmp_media):
        mock_player = self._mock_player()
        with patch("langrepeater.api.state.get_player", return_value=mock_player):
            resp = client.post("/audio/play", json={
                "media_path": str(tmp_media),
                "start": 1.0,
                "end": 3.0,
            })
        assert resp.status_code == 200
        assert resp.json() == {"status": "playing"}
        mock_player.play_segment.assert_called_once_with(str(tmp_media), 1.0, 3.0)

    def test_stop_audio(self, client):
        with patch("langrepeater.api.state.stop_player") as mock_stop:
            resp = client.post("/audio/stop")
        assert resp.status_code == 200
        assert resp.json() == {"status": "stopped"}
        mock_stop.assert_called_once()

    def test_play_audio_error(self, client, tmp_media):
        with patch("langrepeater.api.state.get_player", side_effect=RuntimeError("boom")):
            resp = client.post("/audio/play", json={
                "media_path": str(tmp_media),
                "start": 0.0,
                "end": 1.0,
            })
        assert resp.status_code == 500
        assert "boom" in resp.json()["detail"]


# ---------------------------------------------------------------------------
# /sessions
# ---------------------------------------------------------------------------


class TestSessionsRoutes:
    def test_get_sessions_empty(self, client, progress_store):
        resp = client.get("/sessions/")
        assert resp.status_code == 200
        assert resp.json() == []

    def test_upsert_and_get_session(self, client, progress_store):
        payload = {"media_path": "/a.mp3", "srt_path": "/a.srt", "current_index": 5}
        resp = client.post("/sessions/", json=payload)
        assert resp.status_code == 200
        assert resp.json() == {"status": "saved"}

        resp = client.get("/sessions/")
        assert resp.status_code == 200
        sessions = resp.json()
        assert len(sessions) == 1
        assert sessions[0]["media_path"] == "/a.mp3"
        assert sessions[0]["current_index"] == 5

    def test_upsert_updates_existing(self, client, progress_store):
        client.post("/sessions/", json={"media_path": "/a.mp3", "srt_path": "/a.srt", "current_index": 0})
        client.post("/sessions/", json={"media_path": "/a.mp3", "srt_path": "/a.srt", "current_index": 10})

        resp = client.get("/sessions/")
        sessions = resp.json()
        assert len(sessions) == 1
        assert sessions[0]["current_index"] == 10

    def test_delete_session(self, client, progress_store):
        client.post("/sessions/", json={"media_path": "/a.mp3", "srt_path": "/a.srt", "current_index": 0})
        client.post("/sessions/", json={"media_path": "/b.mp3", "srt_path": "/b.srt", "current_index": 0})

        resp = client.request("DELETE", "/sessions/", json={"media_path": "/a.mp3"})
        assert resp.status_code == 200
        assert resp.json() == {"status": "deleted"}

        resp = client.get("/sessions/")
        sessions = resp.json()
        assert len(sessions) == 1
        assert sessions[0]["media_path"] == "/b.mp3"

    def test_delete_nonexistent_session(self, client, progress_store):
        resp = client.request("DELETE", "/sessions/", json={"media_path": "/nonexistent.mp3"})
        assert resp.status_code == 200
        assert resp.json() == {"status": "deleted"}


# ---------------------------------------------------------------------------
# /stats
# ---------------------------------------------------------------------------


class TestStatsRoutes:
    def test_get_stats_new_media(self, client, stats_store):
        resp = client.get("/stats/", params={"media_path": "/a.mp3"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["media_path"] == "/a.mp3"
        assert data["total_play_count"] == 0
        assert data["subtitle_play_counts"] == {}

    def test_increment_and_get_stats(self, client, stats_store):
        client.post("/stats/increment", json={"media_path": "/a.mp3", "subtitle_index": 1})
        client.post("/stats/increment", json={"media_path": "/a.mp3", "subtitle_index": 1})
        client.post("/stats/increment", json={"media_path": "/a.mp3", "subtitle_index": 2})

        resp = client.get("/stats/", params={"media_path": "/a.mp3"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["total_play_count"] == 3
        # JSON keys are strings
        counts = {int(k): v for k, v in data["subtitle_play_counts"].items()}
        assert counts[1] == 2
        assert counts[2] == 1
