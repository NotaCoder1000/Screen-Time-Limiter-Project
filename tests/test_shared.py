"""
tests/test_shared.py — Unit tests for shared.py utilities.

Covers:
  - Password hashing and verification
  - Token encrypt/decrypt (DPAPI mocked so tests run without pywin32)
  - Config schema validation
  - is_weekend()
"""

import base64
import sys
import types
from pathlib import Path
from unittest.mock import MagicMock

import pytest

# ── Mock win32crypt before importing shared so DPAPI tests work without pywin32 ──
_win32crypt = types.ModuleType("win32crypt")
_win32crypt.CryptProtectData = lambda data, *a, **k: b"\x00MOCK\x00" + data
_win32crypt.CryptUnprotectData = lambda data, *a, **k: (b"desc", data[len(b"\x00MOCK\x00"):])
sys.modules.setdefault("win32crypt", _win32crypt)

# Add project root to sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from shared import (
    check_password,
    decrypt_token,
    encrypt_token,
    hash_password,
    is_weekend,
    validate_config,
)


# ── Password helpers ───────────────────────────────────────────────────────────

class TestPasswordHelpers:
    def test_hash_and_verify_correct(self):
        pw = "correct-horse-battery-staple"
        assert check_password(pw, hash_password(pw))

    def test_hash_and_verify_wrong(self):
        assert not check_password("wrongpassword", hash_password("rightpassword"))

    def test_empty_password_does_not_match_hash(self):
        assert not check_password("", hash_password("something"))

    def test_hashes_are_distinct(self):
        pw = "samepassword"
        assert hash_password(pw) != hash_password(pw)  # bcrypt salts differ each call

    def test_check_bad_hash_returns_false(self):
        assert not check_password("anything", "not-a-valid-bcrypt-hash")


# ── Token encrypt / decrypt ────────────────────────────────────────────────────

class TestTokenEncryptDecrypt:
    def test_roundtrip(self):
        token = "ghp_ABCdef1234567890"
        encrypted = encrypt_token(token)
        assert encrypted.startswith("dpapi:")
        assert decrypt_token(encrypted) == token

    def test_empty_encrypt_returns_empty(self):
        assert encrypt_token("") == ""

    def test_empty_decrypt_returns_empty(self):
        assert decrypt_token("") == ""

    def test_legacy_plaintext_passthrough(self):
        """Values without the 'dpapi:' prefix are returned as-is (legacy compat)."""
        plain = "old_plain_token_without_prefix"
        assert decrypt_token(plain) == plain

    def test_encrypted_value_is_not_plaintext(self):
        token = "super_secret_token"
        encrypted = encrypt_token(token)
        assert token not in encrypted


# ── Config validation ──────────────────────────────────────────────────────────

class TestValidateConfig:
    def test_empty_dict_gets_all_defaults(self):
        result = validate_config({})
        assert result["enabled"] is True
        assert result["blocked_apps"] == []
        assert result["github_username"] == ""
        assert result["github_token"] == ""
        assert result["password_hash"] == ""

    def test_valid_values_are_preserved(self):
        cfg = {
            "enabled": False,
            "blocked_apps": ["steam.exe", "chrome.exe"],
            "github_username": "alice",
        }
        result = validate_config(cfg)
        assert result["enabled"] is False
        assert result["blocked_apps"] == ["steam.exe", "chrome.exe"]
        assert result["github_username"] == "alice"

    def test_wrong_type_falls_back_to_default(self):
        # "enabled" should be bool; a string triggers the fallback
        result = validate_config({"enabled": "yes"})
        assert result["enabled"] is True  # schema default

    def test_null_list_falls_back_to_empty(self):
        result = validate_config({"blocked_apps": None})
        assert result["blocked_apps"] == []

    def test_extra_keys_are_preserved(self):
        result = validate_config({"my_future_key": 42})
        assert result["my_future_key"] == 42

    def test_defaults_are_not_shared_mutable(self):
        r1 = validate_config({})
        r2 = validate_config({})
        r1["blocked_apps"].append("test.exe")
        assert r2["blocked_apps"] == []  # must not affect r2


# ── is_weekend ─────────────────────────────────────────────────────────────────

class TestIsWeekend:
    def test_returns_bool(self):
        assert isinstance(is_weekend(), bool)

    def test_monday_is_not_weekend(self, monkeypatch):
        import datetime
        # Monday = weekday 0
        monkeypatch.setattr(
            "shared.datetime.date",
            type("FakeDate", (), {"today": staticmethod(lambda: datetime.date(2025, 1, 6))}),
        )
        assert not is_weekend()

    def test_saturday_is_weekend(self, monkeypatch):
        import datetime
        # Saturday = weekday 5
        monkeypatch.setattr(
            "shared.datetime.date",
            type("FakeDate", (), {"today": staticmethod(lambda: datetime.date(2025, 1, 4))}),
        )
        assert is_weekend()
