"""
shared.py — Paths, config helpers, logging, and shared utilities.
"""

import copy
import datetime
import json
import logging
import os
import subprocess
import base64
import bcrypt
from logging.handlers import RotatingFileHandler
from pathlib import Path

# ── Paths ──────────────────────────────────────────────────────────────────────
APP_DIR          = Path(os.environ["APPDATA"]) / "ScreenLimiter"
CONFIG_FILE      = APP_DIR / "config.json"
ASSIGNMENTS_FILE = APP_DIR / "assignments.json"
LOG_FILE         = APP_DIR / "limiter.log"

APP_DIR.mkdir(parents=True, exist_ok=True)

# ── Logging ────────────────────────────────────────────────────────────────────

def _setup_logger() -> logging.Logger:
    logger = logging.getLogger("screen_limiter")
    if logger.handlers:
        return logger  # already configured (guard against multiple imports)
    logger.setLevel(logging.DEBUG)
    fmt = logging.Formatter(
        "%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    try:
        fh = RotatingFileHandler(
            LOG_FILE, maxBytes=1_048_576, backupCount=3, encoding="utf-8"
        )
        fh.setFormatter(fmt)
        logger.addHandler(fh)
    except Exception:
        pass  # Can't open log file — console-only fallback
    ch = logging.StreamHandler()
    ch.setFormatter(fmt)
    logger.addHandler(ch)
    return logger


_logger = _setup_logger()


def log(msg: str, level: str = "info") -> None:
    """Write msg to the rotating log file (and stdout). level: debug/info/warning/error."""
    getattr(_logger, level, _logger.info)(msg)


# ── Config schema & validation ─────────────────────────────────────────────────
# Single source of truth for key names, expected types, and defaults.
# validate_config() is called by load_config() so callers always get clean data.

CONFIG_SCHEMA: dict[str, tuple] = {
    "github_username": (str,  ""),
    "github_token":    (str,  ""),
    "blocked_apps":    (list, []),   # list of exe names, e.g. ["steam.exe"]
    "password_hash":   (str,  ""),   # bcrypt hash
    "enabled":         (bool, True),
}

# Expose as DEFAULT_CONFIG for backwards-compatible imports
DEFAULT_CONFIG: dict = {k: copy.deepcopy(v) for k, (_, v) in CONFIG_SCHEMA.items()}


def validate_config(cfg: dict) -> dict:
    """
    Return a validated copy of cfg.
    Any key with the wrong type is replaced by its schema default.
    Unknown keys are preserved (forward-compatibility).
    """
    result: dict = {}
    for key, (expected_type, default) in CONFIG_SCHEMA.items():
        val = cfg.get(key, copy.deepcopy(default))
        if not isinstance(val, expected_type):
            log(
                f"Config '{key}': expected {expected_type.__name__}, "
                f"got {type(val).__name__} — using default.",
                level="warning",
            )
            val = copy.deepcopy(default)
        result[key] = val
    # Preserve keys not in schema (future config additions)
    for key, val in cfg.items():
        if key not in CONFIG_SCHEMA:
            result[key] = val
    return result


# ── Config helpers ─────────────────────────────────────────────────────────────

def load_config() -> dict:
    if not CONFIG_FILE.exists():
        save_config(DEFAULT_CONFIG)
        return copy.deepcopy(DEFAULT_CONFIG)
    with open(CONFIG_FILE, "r") as f:
        data = json.load(f)
    return validate_config(data)


def save_config(cfg: dict) -> None:
    with open(CONFIG_FILE, "w") as f:
        json.dump(cfg, f, indent=2)


# ── Assignment helpers ─────────────────────────────────────────────────────────

def load_assignments() -> list:
    """Return list of {id, text, done} dicts."""
    if not ASSIGNMENTS_FILE.exists():
        return []
    with open(ASSIGNMENTS_FILE, "r") as f:
        return json.load(f)


def save_assignments(assignments: list) -> None:
    with open(ASSIGNMENTS_FILE, "w") as f:
        json.dump(assignments, f, indent=2)


def all_assignments_done() -> bool:
    assignments = load_assignments()
    if not assignments:
        return False   # No assignments defined = not done (prevents trivial bypass)
    return all(a["done"] for a in assignments)


# ── Policy helpers ─────────────────────────────────────────────────────────────

def is_weekend() -> bool:
    """True on Saturday (5) and Sunday (6) in local time."""
    return datetime.date.today().weekday() >= 5


# ── Token encryption (Windows DPAPI) ───────────────────────────────────────────
# Encrypts the GitHub token at rest using the current Windows user's DPAPI key.
# IMPORTANT: encrypt and decrypt MUST run under the same Windows user account.
#
# Deployment context: both main_ui.exe and enforcer.exe run under the interactive
# user (schtasks /IT flag + HKCU Run key), so DPAPI keys are always available.
# If you ever run the enforcer as a different account (e.g. SYSTEM), switch to
# machine-scope DPAPI (flag=CRYPTPROTECT_LOCAL_MACHINE) or Windows Credential Manager.
#
# Stored as "dpapi:<base64>" so legacy plaintext values are still read gracefully.

_DPAPI_PREFIX = "dpapi:"


def encrypt_token(plaintext: str) -> str:
    """Encrypt a string with Windows DPAPI. Returns a 'dpapi:<base64>' string."""
    if not plaintext:
        return ""
    try:
        import win32crypt
        encrypted = win32crypt.CryptProtectData(
            plaintext.encode("utf-8"),
            "ScreenLimiter",
            None, None, None,
            0,
        )
        return _DPAPI_PREFIX + base64.b64encode(encrypted).decode("ascii")
    except Exception as e:
        log(f"encrypt_token failed (storing plaintext as fallback): {e}", level="warning")
        return plaintext


def decrypt_token(stored: str) -> str:
    """Decrypt a DPAPI-encrypted token. Transparently handles legacy plaintext."""
    if not stored:
        return ""
    if not stored.startswith(_DPAPI_PREFIX):
        # Legacy plaintext — return as-is (will be re-encrypted on next save)
        return stored
    try:
        import win32crypt
        encrypted = base64.b64decode(stored[len(_DPAPI_PREFIX):])
        _desc, plaintext = win32crypt.CryptUnprotectData(encrypted, None, None, None, 0)
        return plaintext.decode("utf-8")
    except Exception as e:
        log(f"decrypt_token failed: {e}", level="error")
        return ""


# ── Password helpers ───────────────────────────────────────────────────────────

def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


def check_password(password: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(password.encode(), hashed.encode())
    except Exception:
        return False


# ── Security: config directory hardening ───────────────────────────────────────

def ensure_secure_app_dir() -> None:
    """
    Apply restrictive ACLs to APP_DIR so only the current user and SYSTEM
    can read/write it.  Uses icacls (always present on Windows 7+).
    Safe to call repeatedly — icacls /grant:r is idempotent.
    Call this once at startup from enforcer.py and main_ui.py.
    """
    try:
        username = os.environ.get("USERNAME", "")
        if not username:
            log("ensure_secure_app_dir: USERNAME env var not set, skipping.", level="warning")
            return
        result = subprocess.run(
            [
                "icacls", str(APP_DIR),
                "/inheritance:r",
                "/grant:r", f"{username}:(OI)(CI)F",
                "/grant:r", "SYSTEM:(OI)(CI)F",
            ],
            capture_output=True,
            check=False,
        )
        if result.returncode == 0:
            log("Config directory ACLs hardened (user + SYSTEM only).")
        else:
            log(
                f"icacls returned non-zero: {result.stderr.decode(errors='replace').strip()}",
                level="warning",
            )
    except Exception as e:
        log(f"ensure_secure_app_dir: {e}", level="warning")
