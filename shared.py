"""
shared.py — Paths, config helpers, and state shared across all modules.
"""

import json
import os
import base64
import bcrypt
from pathlib import Path

# ── Paths ──────────────────────────────────────────────────────────────────────
# Everything lives in a hidden folder under AppData so casual users can't find it easily.
APP_DIR       = Path(os.environ["APPDATA"]) / "ScreenLimiter"
CONFIG_FILE   = APP_DIR / "config.json"
ASSIGNMENTS_FILE = APP_DIR / "assignments.json"
LOG_FILE      = APP_DIR / "limiter.log"

APP_DIR.mkdir(parents=True, exist_ok=True)

# ── Default config ─────────────────────────────────────────────────────────────
DEFAULT_CONFIG = {
    "github_username": "",
    "github_token": "",
    "blocked_apps": [],          # list of exe names, e.g. ["chrome.exe", "steam.exe"]
    "password_hash": "",         # bcrypt hash of the admin password
    "enabled": True
}

# ── Config helpers ─────────────────────────────────────────────────────────────

def load_config() -> dict:
    if not CONFIG_FILE.exists():
        save_config(DEFAULT_CONFIG)
        return dict(DEFAULT_CONFIG)
    with open(CONFIG_FILE, "r") as f:
        data = json.load(f)
    # Fill in any missing keys from defaults
    for k, v in DEFAULT_CONFIG.items():
        data.setdefault(k, v)
    return data


def save_config(cfg: dict):
    with open(CONFIG_FILE, "w") as f:
        json.dump(cfg, f, indent=2)


# ── Assignment helpers ─────────────────────────────────────────────────────────

def load_assignments() -> list:
    """Return list of {id, text, done} dicts."""
    if not ASSIGNMENTS_FILE.exists():
        return []
    with open(ASSIGNMENTS_FILE, "r") as f:
        return json.load(f)


def save_assignments(assignments: list):
    with open(ASSIGNMENTS_FILE, "w") as f:
        json.dump(assignments, f, indent=2)


def all_assignments_done() -> bool:
    assignments = load_assignments()
    if not assignments:
        return False   # No assignments defined = not done (prevents trivial bypass)
    return all(a["done"] for a in assignments)


# ── Token encryption (Windows DPAPI) ───────────────────────────────────────────
# Encrypts the GitHub token at rest using the current Windows user's credentials.
# Only the same user account on the same machine can decrypt it.
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
            "ScreenLimiter",  # description (ignored on decrypt, just for logging)
            None, None, None,
            0,
        )
        return _DPAPI_PREFIX + base64.b64encode(encrypted).decode("ascii")
    except Exception as e:
        log(f"encrypt_token failed (storing plaintext as fallback): {e}")
        return plaintext  # fallback: store as-is rather than lose the value


def decrypt_token(stored: str) -> str:
    """Decrypt a DPAPI-encrypted token. Transparently handles legacy plaintext."""
    if not stored:
        return ""
    if not stored.startswith(_DPAPI_PREFIX):
        # Legacy plaintext value — return as-is (will be re-encrypted on next save)
        return stored
    try:
        import win32crypt
        encrypted = base64.b64decode(stored[len(_DPAPI_PREFIX):])
        _desc, plaintext = win32crypt.CryptUnprotectData(
            encrypted, None, None, None, 0
        )
        return plaintext.decode("utf-8")
    except Exception as e:
        log(f"decrypt_token failed: {e}")
        return ""


# ── Password helpers ───────────────────────────────────────────────────────────

def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


def check_password(password: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(password.encode(), hashed.encode())
    except Exception:
        return False


# ── Logging ────────────────────────────────────────────────────────────────────

def log(msg: str):
    import datetime
    timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{timestamp}] {msg}\n"
    with open(LOG_FILE, "a") as f:
        f.write(line)
    print(line, end="")
