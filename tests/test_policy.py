"""
tests/test_policy.py — Unit tests for core.py policy evaluation.
"""

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

# Stub Windows-only modules
for _mod in ("win32crypt", "win32api", "win32con", "win32process", "pywintypes", "wmi"):
    sys.modules.setdefault(_mod, MagicMock())

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core import is_blocked, should_enforce


class TestShouldEnforce:
    @patch("core.is_weekend", return_value=False)
    def test_enabled_weekday(self, _):
        assert should_enforce({"enabled": True}) is True

    @patch("core.is_weekend", return_value=False)
    def test_disabled_weekday(self, _):
        assert should_enforce({"enabled": False}) is False

    @patch("core.is_weekend", return_value=True)
    def test_weekend_always_off(self, _):
        assert should_enforce({"enabled": True}) is False

    @patch("core.is_weekend", return_value=False)
    def test_missing_enabled_defaults_true(self, _):
        assert should_enforce({}) is True


class TestIsBlocked:
    @patch("core.is_weekend", return_value=False)
    def test_blocked_app_detected(self, _):
        cfg = {"enabled": True, "blocked_apps": ["steam.exe", "chrome.exe"]}
        assert is_blocked("steam.exe", cfg) is True

    @patch("core.is_weekend", return_value=False)
    def test_case_insensitive(self, _):
        cfg = {"enabled": True, "blocked_apps": ["Steam.exe"]}
        assert is_blocked("STEAM.EXE", cfg) is True

    @patch("core.is_weekend", return_value=False)
    def test_unlisted_app_not_blocked(self, _):
        cfg = {"enabled": True, "blocked_apps": ["steam.exe"]}
        assert is_blocked("notepad.exe", cfg) is False

    @patch("core.is_weekend", return_value=False)
    def test_empty_blocked_list(self, _):
        cfg = {"enabled": True, "blocked_apps": []}
        assert is_blocked("anything.exe", cfg) is False

    @patch("core.is_weekend", return_value=False)
    def test_limiter_disabled_never_blocks(self, _):
        cfg = {"enabled": False, "blocked_apps": ["steam.exe"]}
        assert is_blocked("steam.exe", cfg) is False

    @patch("core.is_weekend", return_value=True)
    def test_weekend_never_blocks(self, _):
        cfg = {"enabled": True, "blocked_apps": ["steam.exe"]}
        assert is_blocked("steam.exe", cfg) is False
