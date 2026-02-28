"""
core.py — Policy evaluation for Screen Limiter.

Extracted from enforcer/popup/tray to eliminate duplication and give
callers a single, testable API for "should this app be blocked right now?".
"""

from shared import all_assignments_done, is_weekend, load_config, log


def should_enforce(cfg: dict | None = None) -> bool:
    """
    Return True if the limiter is active right now:
      - Not a weekend, AND
      - cfg["enabled"] is True.
    """
    if is_weekend():
        return False
    if cfg is None:
        cfg = load_config()
    return bool(cfg.get("enabled", True))


def is_blocked(process_name: str, cfg: dict | None = None) -> bool:
    """
    Return True if process_name is on the blocked list and enforcement is active.
    process_name is compared case-insensitively.
    """
    if cfg is None:
        cfg = load_config()
    if not should_enforce(cfg):
        return False
    blocked = {b.lower() for b in cfg.get("blocked_apps", [])}
    return process_name.lower() in blocked
