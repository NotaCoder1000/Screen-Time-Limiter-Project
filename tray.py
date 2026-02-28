"""
tray.py — System tray icon for Screen Limiter.
Provides quick access to assignments manager and settings.
Runs at startup as a normal user process (not the service).
"""

import sys
import os
import subprocess
import threading
import datetime

import pystray
from PIL import Image, ImageDraw

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from shared import load_assignments, all_assignments_done, load_config, log

# When frozen by PyInstaller, sys.executable is tray.exe itself.
# Sibling exes live in the same directory.
if getattr(sys, "frozen", False):
    SERVICE_DIR = os.path.dirname(sys.executable)
else:
    SERVICE_DIR = os.path.dirname(os.path.abspath(__file__))


def get_icon_image(status: str) -> Image.Image:
    """
    status: 'allowed' (green), 'blocked' (red), 'weekend' (blue)
    Returns a 64x64 PIL image.
    """
    colors = {
        "allowed": ((34, 197, 94),   (21, 128, 61)),    # green
        "blocked": ((239, 68, 68),   (185, 28, 28)),    # red
        "weekend": ((59, 130, 246),  (29, 78, 216)),    # blue
    }
    main_color, shadow = colors.get(status, colors["blocked"])

    img = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
    d   = ImageDraw.Draw(img)
    # Shadow
    d.ellipse([6, 6, 60, 60], fill=(*shadow, 180))
    # Main circle
    d.ellipse([4, 4, 58, 58], fill=(*main_color, 255))
    # Inner highlight
    d.ellipse([12, 12, 28, 28], fill=(255, 255, 255, 60))

    return img


def current_status() -> tuple[str, str]:
    """Returns (status_key, tooltip_text)."""
    if datetime.date.today().weekday() >= 5:
        return "weekend", "Screen Limiter — Weekend, all apps unlocked"

    cfg = load_config()
    if not cfg.get("enabled", True):
        return "allowed", "Screen Limiter — Disabled"

    assignments = load_assignments()
    if not assignments:
        return "blocked", "Screen Limiter — No assignments set (apps blocked)"

    done = all_assignments_done()
    if done:
        return "allowed", "Screen Limiter — Assignments done ✓ (GitHub checked on launch)"
    else:
        total     = len(assignments)
        done_count = sum(1 for a in assignments if a.get("done"))
        return "blocked", f"Screen Limiter — {done_count}/{total} assignments done"


def _launch_main():
    """Launch the combined Screen Limiter control panel."""
    if getattr(sys, "frozen", False):
        path = os.path.join(SERVICE_DIR, "main.exe")
        subprocess.Popen([path])
    else:
        pythonw = sys.executable.replace("python.exe", "pythonw.exe")
        if not os.path.exists(pythonw):
            pythonw = sys.executable
        subprocess.Popen([pythonw, os.path.join(SERVICE_DIR, "main_ui.py")])


def build_menu(icon):
    def assignments_label(item):
        assignments = load_assignments()
        done  = sum(1 for a in assignments if a.get("done"))
        total = len(assignments)
        return f"Assignments: {done}/{total} done"

    return pystray.Menu(
        pystray.MenuItem(assignments_label, None, enabled=False),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem("🛡  Open Screen Limiter", lambda icon, item: _launch_main()),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem("Quit Tray (service keeps running)", lambda icon, item: icon.stop()),
    )


def status_update_loop(icon):
    """Refresh the tray icon color every 30 seconds."""
    while True:
        import time
        status, tooltip = current_status()
        icon.icon  = get_icon_image(status)
        icon.title = tooltip
        time.sleep(30)


def main():
    status, tooltip = current_status()
    icon = pystray.Icon(
        "ScreenLimiter",
        icon=get_icon_image(status),
        title=tooltip,
        menu=build_menu(None)
    )
    icon.menu = build_menu(icon)

    threading.Thread(target=status_update_loop, args=(icon,), daemon=True).start()
    log("Tray started.")
    icon.run()


if __name__ == "__main__":
    main()
