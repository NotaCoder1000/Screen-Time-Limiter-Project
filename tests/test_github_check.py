"""
tests/test_github_check.py — Unit tests for github_check.has_commit_today().

All HTTP calls are mocked. All dates are computed in UTC so tests are
timezone-independent.
"""

import datetime
import sys
import types
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# ── Stub out windows-only modules before importing project code ────────────────
for _mod in ("win32crypt", "win32api", "win32con", "win32process", "pywintypes", "wmi"):
    sys.modules.setdefault(_mod, MagicMock())

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from github_check import has_commit_today, _parse_event_date, _today_utc


# ── Helper builders ────────────────────────────────────────────────────────────

def _iso(dt: datetime.datetime) -> str:
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def _event(event_type: str, dt: datetime.datetime, repo: str = "user/repo") -> dict:
    return {"type": event_type, "created_at": _iso(dt), "repo": {"name": repo}}


def _now_utc() -> datetime.datetime:
    return datetime.datetime.now(datetime.timezone.utc)


def _make_mock_response(events: list, status: int = 200) -> MagicMock:
    resp = MagicMock()
    resp.status_code = status
    resp.json.return_value = events
    return resp


# ── _parse_event_date ──────────────────────────────────────────────────────────

class TestParseEventDate:
    def test_valid_utc_timestamp(self):
        result = _parse_event_date("2025-01-15T10:30:00Z")
        assert result == datetime.date(2025, 1, 15)

    def test_invalid_returns_none(self):
        assert _parse_event_date("not-a-date") is None

    def test_empty_returns_none(self):
        assert _parse_event_date("") is None


# ── has_commit_today: Events API ───────────────────────────────────────────────

class TestEventsApi:
    @patch("github_check.requests.get")
    @patch("github_check.decrypt_token", return_value="")
    @patch("github_check.load_config")
    def test_push_event_today_returns_true(self, mock_cfg, mock_decrypt, mock_get):
        mock_cfg.return_value = {"github_username": "alice", "github_token": ""}
        today_event = _event("PushEvent", _now_utc(), repo="alice/myrepo")
        mock_get.return_value = _make_mock_response([today_event])

        found, reason = has_commit_today()

        assert found is True
        assert "alice/myrepo" in reason

    @patch("github_check.requests.get")
    @patch("github_check.decrypt_token", return_value="")
    @patch("github_check.load_config")
    def test_create_event_today_returns_true(self, mock_cfg, mock_decrypt, mock_get):
        mock_cfg.return_value = {"github_username": "alice", "github_token": ""}
        today_event = _event("CreateEvent", _now_utc())
        mock_get.return_value = _make_mock_response([today_event])

        found, reason = has_commit_today()
        assert found is True

    @patch("github_check.requests.get")
    @patch("github_check.decrypt_token", return_value="")
    @patch("github_check.load_config")
    def test_only_yesterday_event_returns_false(self, mock_cfg, mock_decrypt, mock_get):
        mock_cfg.return_value = {"github_username": "alice", "github_token": ""}
        yesterday = _now_utc() - datetime.timedelta(days=1)
        old_event = _event("PushEvent", yesterday)
        mock_get.return_value = _make_mock_response([old_event])

        found, _ = has_commit_today()
        assert found is False

    @patch("github_check.requests.get")
    @patch("github_check.decrypt_token", return_value="")
    @patch("github_check.load_config")
    def test_non_push_event_type_ignored(self, mock_cfg, mock_decrypt, mock_get):
        mock_cfg.return_value = {"github_username": "alice", "github_token": ""}
        # IssuesEvent today — should NOT count as a commit
        issues_event = _event("IssuesEvent", _now_utc())
        mock_get.return_value = _make_mock_response([issues_event])

        found, _ = has_commit_today()
        assert found is False

    @patch("github_check.requests.get")
    @patch("github_check.decrypt_token", return_value="")
    @patch("github_check.load_config")
    def test_empty_events_returns_false(self, mock_cfg, mock_decrypt, mock_get):
        mock_cfg.return_value = {"github_username": "alice", "github_token": ""}
        mock_get.return_value = _make_mock_response([])

        found, _ = has_commit_today()
        assert found is False

    @patch("github_check.requests.get")
    @patch("github_check.decrypt_token", return_value="")
    @patch("github_check.load_config")
    def test_api_error_status_falls_through(self, mock_cfg, mock_decrypt, mock_get):
        mock_cfg.return_value = {"github_username": "alice", "github_token": ""}
        mock_get.return_value = _make_mock_response([], status=403)

        found, _ = has_commit_today()
        assert found is False

    @patch("github_check.requests.get")
    @patch("github_check.decrypt_token", return_value="")
    @patch("github_check.load_config")
    def test_pagination_stops_on_older_event(self, mock_cfg, mock_decrypt, mock_get):
        """
        Page 1 has only a non-push event from yesterday → pagination must stop.
        Page 2 would have today's push but should never be fetched.
        """
        mock_cfg.return_value = {"github_username": "alice", "github_token": ""}
        yesterday = _now_utc() - datetime.timedelta(days=1)
        page1 = [_event("IssuesEvent", yesterday)]  # no push, older than today
        page2 = [_event("PushEvent", _now_utc())]   # today but should not be reached

        mock_get.side_effect = [
            _make_mock_response(page1),
            _make_mock_response(page2),
        ]
        found, _ = has_commit_today()

        # Should have stopped after page 1 (older event found), so NOT found
        assert found is False
        assert mock_get.call_count == 1  # only one request made


# ── has_commit_today: missing config ──────────────────────────────────────────

class TestMissingConfig:
    @patch("github_check.load_config")
    def test_no_username_returns_false_with_message(self, mock_cfg):
        mock_cfg.return_value = {"github_username": "", "github_token": ""}
        found, reason = has_commit_today()
        assert found is False
        assert "not configured" in reason.lower()

    @patch("github_check.requests.get")
    @patch("github_check.decrypt_token", return_value="")
    @patch("github_check.load_config")
    def test_network_exception_returns_false(self, mock_cfg, mock_decrypt, mock_get):
        import requests as req
        mock_cfg.return_value = {"github_username": "alice", "github_token": ""}
        mock_get.side_effect = req.RequestException("timeout")
        found, _ = has_commit_today()
        assert found is False


# ── has_commit_today: Search API fallback ─────────────────────────────────────

class TestSearchApiFallback:
    @patch("github_check.requests.get")
    @patch("github_check.decrypt_token", return_value="mytoken")
    @patch("github_check.load_config")
    def test_search_api_finds_commit_when_events_empty(self, mock_cfg, mock_decrypt, mock_get):
        mock_cfg.return_value = {"github_username": "alice", "github_token": "dpapi:ignored"}

        events_resp = _make_mock_response([])  # Events API: nothing
        search_resp = MagicMock()
        search_resp.status_code = 200
        search_resp.json.return_value = {"total_count": 3}

        mock_get.side_effect = [events_resp, search_resp]

        found, reason = has_commit_today()
        assert found is True
        assert "3" in reason
