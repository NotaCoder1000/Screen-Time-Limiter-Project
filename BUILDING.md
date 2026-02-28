# Building the Screen Limiter Installer

This produces a single `ScreenLimiter-Setup.exe` that installs everything with
no Python dependency on the target machine.

---

## Prerequisites (one-time setup on YOUR machine)

### 1. Python + dependencies
```
pip install -r requirements.txt
pip install pyinstaller
```

### 2. NSIS (Nullsoft Scriptable Install System)
Download and install from https://nsis.sourceforge.io/Download
Version 3.x, default install location is fine.
After install, make sure `makensis` is in your PATH, or use the NSIS GUI.

---

## Build Steps

### Step 1 — Bundle Python scripts into .exe files
```
python build.py
```
This runs PyInstaller for each component and places the results in:
```
dist\ScreenLimiter\
    enforcer.exe   — Background monitor (console, runs at logon via Task Scheduler)
    popup.exe      — Interception popup (windowed)
    tray.exe       — System tray icon (windowed)
    main.exe       — Combined control panel UI (windowed)
```
This takes a few minutes — PyInstaller packages the entire Python runtime and all
dependencies into each exe.

### Step 2 — Compile the NSIS installer
Option A — command line:
```
makensis installer.nsi
```

Option B — GUI:
Right-click `installer.nsi` → "Compile NSIS Script"

Output: `ScreenLimiter-Setup.exe` in the project root.

---

## What the installer does

When a user runs `ScreenLimiter-Setup.exe`:

1. **Welcome page** — shows app name and version
2. **Directory page** — defaults to `C:\Program Files\ScreenLimiter`
3. **Install page** — copies files, registers scheduled task, writes registry
4. **Finish page** — Settings window opens automatically for first-time config

Registry entries written:
```
HKLM\SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\ScreenLimiter\
    DisplayName        = "Screen Limiter"
    DisplayVersion     = "1.0.0"
    Publisher          = "You"
    InstallLocation    = "C:\Program Files\ScreenLimiter"
    UninstallString    = "C:\Program Files\ScreenLimiter\Uninstall.exe"
    DisplayIcon        = "C:\Program Files\ScreenLimiter\tray.exe"
    NoModify           = 1
    NoRepair           = 1

HKCU\SOFTWARE\Microsoft\Windows\CurrentVersion\Run\
    ScreenLimiterTray  = "C:\Program Files\ScreenLimiter\tray.exe"
```

The enforcer is registered as a **Task Scheduler** task (`ScreenLimiterMonitor`) with:
- Trigger: At logon (`/SC ONLOGON`)
- Privilege: Highest (`/RL HIGHEST`)
- Mode: Interactive user session (`/IT`)

`enforcer.exe` is **not** a Windows Service — it uses Task Scheduler to run elevated
in the user's session without the SCM 30-second startup timeout.

---

## Uninstalling

Via **Add/Remove Programs** (Settings → Apps) or by running
`C:\Program Files\ScreenLimiter\Uninstall.exe`.

The uninstaller kills the enforcer, removes the scheduled task, removes all registry
entries, removes Start Menu shortcuts, and deletes the install directory.

Your personal data (`%APPDATA%\ScreenLimiter\`) is intentionally preserved —
delete that folder manually if you want a completely clean removal.
