"""Tests for the macOS app layer (Phase 3).

LangRepeaterClient is tested with a mocked httpx.Client.
AppController is tested with a mocked LangRepeaterClient.
The tkinter GUI (app.py) is not tested directly as it requires a display
and an event loop; its logic lives in AppController and LangRepeaterClient.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from langrepeater.macos_app.api_client import LangRepeaterClient
from langrepeater.macos_app.controller import AppController, AppState


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_response(json_data, status_code: int = 200):
    resp = MagicMock()
    resp.status_code = status_code
    resp.json.return_value = json_data
    resp.raise_for_status.return_value = None
    return resp


SAMPLE_SUBS = [
    {"index": 1, "start": 1.0, "end": 3.0, "text": "Hello"},
    {"index": 2, "start": 4.0, "end": 6.0, "text": "World"},
    {"index": 3, "start": 7.0, "end": 9.0, "text": "Bye"},
]


# ---------------------------------------------------------------------------
# LangRepeaterClient tests
# ---------------------------------------------------------------------------

class TestLangRepeaterClient:
    @pytest.fixture()
    def http(self):
        with patch("langrepeater.macos_app.api_client.httpx.Client") as cls:
            mock_http = MagicMock()
            cls.return_value = mock_http
            yield mock_http

    @pytest.fixture()
    def client(self, http):
        return LangRepeaterClient()

    # Files ----------------------------------------------------------------

    def test_find_media(self, client, http):
        http.get.return_value = _make_response(["/a.mp3", "/b.mp4"])
        result = client.find_media("/some/dir")
        http.get.assert_called_once_with("/files/media", params={"directory": "/some/dir"})
        assert result == ["/a.mp3", "/b.mp4"]

    def test_find_srt(self, client, http):
        http.get.return_value = _make_response(["/sub.srt"])
        result = client.find_srt("/some/dir")
        http.get.assert_called_once_with("/files/srt", params={"directory": "/some/dir"})
        assert result == ["/sub.srt"]

    # Subtitles ------------------------------------------------------------

    def test_get_subtitles(self, client, http):
        http.get.return_value = _make_response(SAMPLE_SUBS)
        result = client.get_subtitles("/a.srt")
        http.get.assert_called_once_with("/subtitles/", params={"srt_path": "/a.srt"})
        assert len(result) == 3
        assert result[0]["text"] == "Hello"

    # Audio ----------------------------------------------------------------

    def test_play(self, client, http):
        http.post.return_value = _make_response({"status": "playing"})
        client.play("/a.mp3", 1.0, 3.0)
        http.post.assert_called_once_with(
            "/audio/play",
            json={"media_path": "/a.mp3", "start": 1.0, "end": 3.0},
        )

    def test_stop(self, client, http):
        http.post.return_value = _make_response({"status": "stopped"})
        client.stop()
        http.post.assert_called_once_with("/audio/stop")

    # Sessions -------------------------------------------------------------

    def test_get_sessions(self, client, http):
        payload = [{"media_path": "/a.mp3", "srt_path": "/a.srt", "current_index": 5}]
        http.get.return_value = _make_response(payload)
        result = client.get_sessions()
        assert result == payload

    def test_upsert_session(self, client, http):
        http.post.return_value = _make_response({"status": "saved"})
        client.upsert_session("/a.mp3", "/a.srt", 7)
        http.post.assert_called_once_with(
            "/sessions/",
            json={"media_path": "/a.mp3", "srt_path": "/a.srt", "current_index": 7},
        )

    def test_delete_session(self, client, http):
        http.request.return_value = _make_response({"status": "deleted"})
        client.delete_session("/a.mp3")
        http.request.assert_called_once_with(
            "DELETE", "/sessions/", json={"media_path": "/a.mp3"}
        )

    # Stats ----------------------------------------------------------------

    def test_get_stats(self, client, http):
        payload = {"media_path": "/a.mp3", "total_play_count": 5, "subtitle_play_counts": {1: 2}}
        http.get.return_value = _make_response(payload)
        result = client.get_stats("/a.mp3")
        assert result["total_play_count"] == 5

    def test_increment_play(self, client, http):
        http.post.return_value = _make_response({"status": "incremented"})
        client.increment_play("/a.mp3", 2)
        http.post.assert_called_once_with(
            "/stats/increment",
            json={"media_path": "/a.mp3", "subtitle_index": 2},
        )

    def test_close(self, client, http):
        client.close()
        http.close.assert_called_once()


# ---------------------------------------------------------------------------
# AppController tests
# ---------------------------------------------------------------------------

class TestAppController:
    @pytest.fixture()
    def mock_client(self):
        c = MagicMock(spec=LangRepeaterClient)
        c.get_subtitles.return_value = SAMPLE_SUBS
        c.get_stats.return_value = {
            "media_path": "/a.mp3",
            "total_play_count": 0,
            "subtitle_play_counts": {},
        }
        return c

    @pytest.fixture()
    def ctrl(self, mock_client):
        return AppController(mock_client)

    # load_files -----------------------------------------------------------

    def test_load_files_sets_state(self, ctrl, mock_client):
        ctrl.load_files("/a.mp3", "/a.srt")
        assert ctrl.state.media_path == "/a.mp3"
        assert ctrl.state.srt_path == "/a.srt"
        assert ctrl.state.subtitles == SAMPLE_SUBS
        assert ctrl.state.current_index == 0

    def test_load_files_resets_index(self, ctrl):
        ctrl.state.current_index = 2
        ctrl.load_files("/a.mp3", "/a.srt")
        assert ctrl.state.current_index == 0

    # resume_session -------------------------------------------------------

    def test_resume_session(self, ctrl, mock_client):
        session = {"media_path": "/a.mp3", "srt_path": "/a.srt", "current_index": 2}
        ctrl.resume_session(session)
        assert ctrl.state.current_index == 2
        assert ctrl.state.media_path == "/a.mp3"

    # navigation -----------------------------------------------------------

    def test_go_next_advances(self, ctrl):
        ctrl.load_files("/a.mp3", "/a.srt")
        result = ctrl.go_next()
        assert result is True
        assert ctrl.state.current_index == 1

    def test_go_next_at_end_returns_false(self, ctrl):
        ctrl.load_files("/a.mp3", "/a.srt")
        ctrl.state.current_index = 2  # last subtitle
        result = ctrl.go_next()
        assert result is False
        assert ctrl.state.current_index == 2

    def test_go_prev_goes_back(self, ctrl):
        ctrl.load_files("/a.mp3", "/a.srt")
        ctrl.state.current_index = 1
        result = ctrl.go_prev()
        assert result is True
        assert ctrl.state.current_index == 0

    def test_go_prev_at_start_returns_false(self, ctrl):
        ctrl.load_files("/a.mp3", "/a.srt")
        result = ctrl.go_prev()
        assert result is False
        assert ctrl.state.current_index == 0

    # play_current ---------------------------------------------------------

    def test_play_current_calls_api(self, ctrl, mock_client):
        ctrl.load_files("/a.mp3", "/a.srt")
        ctrl.play_current()
        mock_client.play.assert_called_once_with("/a.mp3", 1.0, 3.0)
        mock_client.increment_play.assert_called_once_with("/a.mp3", 1)

    def test_play_current_no_subtitles_does_nothing(self, ctrl, mock_client):
        ctrl.play_current()
        mock_client.play.assert_not_called()

    # display_window -------------------------------------------------------

    def test_display_window_at_start(self, ctrl):
        ctrl.load_files("/a.mp3", "/a.srt")
        prev, curr, nxt = ctrl.display_window()
        assert prev is None
        assert curr["text"] == "Hello"
        assert nxt["text"] == "World"

    def test_display_window_middle(self, ctrl):
        ctrl.load_files("/a.mp3", "/a.srt")
        ctrl.state.current_index = 1
        prev, curr, nxt = ctrl.display_window()
        assert prev["text"] == "Hello"
        assert curr["text"] == "World"
        assert nxt["text"] == "Bye"

    def test_display_window_at_end(self, ctrl):
        ctrl.load_files("/a.mp3", "/a.srt")
        ctrl.state.current_index = 2
        prev, curr, nxt = ctrl.display_window()
        assert prev["text"] == "World"
        assert curr["text"] == "Bye"
        assert nxt is None

    def test_display_window_empty(self, ctrl):
        prev, curr, nxt = ctrl.display_window()
        assert prev is None
        assert curr is None
        assert nxt is None

    # progress_text --------------------------------------------------------

    def test_progress_text(self, ctrl):
        ctrl.load_files("/a.mp3", "/a.srt")
        assert ctrl.progress_text() == "1/3  (33%)"
        ctrl.state.current_index = 2
        assert ctrl.progress_text() == "3/3  (100%)"

    def test_progress_text_empty(self, ctrl):
        assert ctrl.progress_text() == ""

    # save_progress --------------------------------------------------------

    def test_save_progress_calls_upsert(self, ctrl, mock_client):
        ctrl.load_files("/a.mp3", "/a.srt")
        ctrl.state.current_index = 1
        ctrl.save_progress()
        mock_client.upsert_session.assert_called_once_with("/a.mp3", "/a.srt", 1)

    def test_save_progress_no_media_does_nothing(self, ctrl, mock_client):
        ctrl.save_progress()
        mock_client.upsert_session.assert_not_called()

    # stop -----------------------------------------------------------------

    def test_stop_calls_api(self, ctrl, mock_client):
        ctrl.stop()
        mock_client.stop.assert_called_once()
