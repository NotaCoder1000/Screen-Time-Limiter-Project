"""
install.py — Setup wizard for Screen Limiter.
Run this ONCE (as Administrator) to:
  1. Install Python dependencies
  2. Walk through first-time configuration
  3. Install and start the Windows Service
  4. Add the tray app to startup
"""

import sys
import os
import subprocess
import shutil
import winreg

# Self-check: must be run as Administrator
import ctypes
if not ctypes.windll.shell32.IsUserAnAdmin():
    print("ERROR: Please run this script as Administrator.")
    print("Right-click install.py → 'Run as administrator'")
    input("Press Enter to exit.")
    sys.exit(1)

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PYTHON     = sys.executable

print("=" * 60)
print("  Screen Limiter — Setup Wizard")
print("=" * 60)
print()

# ── Step 1: Install dependencies ──────────────────────────────────────────────
print("[1/5] Installing Python dependencies…")
req_file = os.path.join(SCRIPT_DIR, "requirements.txt")
result = subprocess.run(
    [PYTHON, "-m", "pip", "install", "-r", req_file, "--quiet"],
    capture_output=True, text=True
)
if result.returncode != 0:
    print("  ERROR during pip install:")
    print(result.stderr)
    input("Press Enter to exit.")
    sys.exit(1)
print("  ✓ Dependencies installed.\n")

# ── Step 2: Import shared after deps are installed ────────────────────────────
sys.path.insert(0, SCRIPT_DIR)
from shared import load_config, save_config, hash_password

# ── Step 3: First-time configuration ─────────────────────────────────────────
print("[2/5] Configuration")
cfg = load_config()

github_user = input(f"  GitHub username [{cfg.get('github_username', '')}]: ").strip()
if github_user:
    cfg["github_username"] = github_user

print("  A GitHub Personal Access Token lets us check private repo commits.")
print("  Get one at: GitHub → Settings → Developer Settings → Tokens → Fine-grained")
print("  Required permissions: none (public events only) or 'repo' for private commits.")
github_token = input(f"  GitHub token (leave blank to skip) [{bool(cfg.get('github_token'))*'***'}]: ").strip()
if github_token:
    cfg["github_token"] = github_token

print()
print("  Blocked apps are configured via the Settings GUI after setup.")
print()

pw1 = input("  Set admin password (protects Settings panel, min 6 chars): ").strip()
while len(pw1) < 6:
    print("  Too short. Try again.")
    pw1 = input("  Set admin password: ").strip()
pw2 = input("  Confirm password: ").strip()
while pw1 != pw2:
    print("  Passwords don't match. Try again.")
    pw1 = input("  Set admin password: ").strip()
    pw2 = input("  Confirm password: ").strip()
cfg["password_hash"] = hash_password(pw1)
cfg["enabled"] = True

save_config(cfg)
print("  ✓ Configuration saved.\n")

# ── Step 4: Install Windows Service ──────────────────────────────────────────
print("[3/5] Installing Windows Service…")
service_script = os.path.join(SCRIPT_DIR, "service.py")

# Remove old service if it exists
subprocess.run([PYTHON, service_script, "remove"], capture_output=True)

result = subprocess.run(
    [PYTHON, service_script, "install"],
    capture_output=True, text=True
)
if result.returncode != 0:
    print("  ERROR installing service:")
    print(result.stderr)
    print(result.stdout)
    input("Press Enter to exit.")
    sys.exit(1)

# Configure service to start automatically
subprocess.run(
    ["sc", "config", "ScreenLimiterSvc", "start=", "auto"],
    capture_output=True
)

# Start service
result = subprocess.run(
    [PYTHON, service_script, "start"],
    capture_output=True, text=True
)
print(f"  Service start: {result.stdout.strip() or 'OK'}")
print("  ✓ Windows Service installed and started.\n")

# ── Step 5: Add tray app to Windows startup ───────────────────────────────────
print("[4/5] Adding tray app to Windows startup…")

pythonw = PYTHON.replace("python.exe", "pythonw.exe")
if not os.path.exists(pythonw):
    pythonw = PYTHON

tray_script = os.path.join(SCRIPT_DIR, "tray.py")
startup_cmd = f'"{pythonw}" "{tray_script}"'

try:
    key = winreg.OpenKey(
        winreg.HKEY_CURRENT_USER,
        r"Software\Microsoft\Windows\CurrentVersion\Run",
        0,
        winreg.KEY_SET_VALUE
    )
    winreg.SetValueEx(key, "ScreenLimiterTray", 0, winreg.REG_SZ, startup_cmd)
    winreg.CloseKey(key)
    print("  ✓ Tray app will launch at Windows startup.\n")
except Exception as e:
    print(f"  Warning: Could not add to startup: {e}")
    print("  You can manually run tray.py to get the tray icon.\n")

# ── Step 6: Launch tray now ───────────────────────────────────────────────────
print("[5/5] Launching tray icon…")
subprocess.Popen([pythonw, tray_script])
print("  ✓ Tray icon launched. Look for the colored dot in your system tray.\n")

print("=" * 60)
print("  Setup complete!")
print()
print("  How it works:")
print("  • A Windows Service (runs even without tray) watches for blocked apps")
print("  • When you open a blocked app, it's paused and a popup appears")
print("  • You must check off all assignments AND have a GitHub commit today")
print("  • Weekends are automatically unlocked")
print()
print("  Tray icon colors:")
print("    🟢 Green  = all checks passed, apps allowed")
print("    🔴 Red    = blocked (missing commit or unchecked assignments)")
print("    🔵 Blue   = weekend mode")
print()
print("  Right-click the tray icon to manage assignments or open settings.")
print("  Settings are password-protected with the password you just set.")
print("=" * 60)
input("\nPress Enter to close setup.")
