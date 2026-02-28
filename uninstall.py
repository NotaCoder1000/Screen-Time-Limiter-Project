"""
uninstall.py — Removes Screen Limiter service and startup entry.
Run as Administrator.
"""

import sys
import os
import subprocess
import winreg
import ctypes

if not ctypes.windll.shell32.IsUserAnAdmin():
    print("ERROR: Run as Administrator.")
    input("Press Enter to exit.")
    sys.exit(1)

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PYTHON = sys.executable

print("Uninstalling Screen Limiter…")

# Stop and remove service
service_script = os.path.join(SCRIPT_DIR, "service.py")
subprocess.run([PYTHON, service_script, "stop"],   capture_output=True)
subprocess.run([PYTHON, service_script, "remove"], capture_output=True)
print("  ✓ Service removed.")

# Remove from startup
try:
    key = winreg.OpenKey(
        winreg.HKEY_CURRENT_USER,
        r"Software\Microsoft\Windows\CurrentVersion\Run",
        0, winreg.KEY_SET_VALUE
    )
    winreg.DeleteValue(key, "ScreenLimiterTray")
    winreg.CloseKey(key)
    print("  ✓ Startup entry removed.")
except FileNotFoundError:
    print("  (Startup entry not found, skipping.)")
except Exception as e:
    print(f"  Warning: {e}")

print("\nDone. You can delete this folder manually if desired.")
input("Press Enter to exit.")
