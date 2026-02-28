"""
settings_ui.py — Retained for backward compatibility only.
The full UI is now in main_ui.py (combined Assignments + Blocked Apps + Admin tabs).
"""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


def open_settings():
    """Redirect to the combined main UI."""
    from main_ui import main
    main()


if __name__ == "__main__":
    open_settings()
