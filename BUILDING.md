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

### 3. Assets folder (optional but recommended)
Create an `assets\` folder next to `installer.nsi` with:
- `icon.ico`         — 256x256 icon for the installer and tray exe
- `wizard_banner.bmp` — 164×314 px banner shown on the Welcome page

If you skip this, edit `installer.nsi` and remove the three `!define MUI_*BITMAP`
and `!define MUI_*ICON` lines, and NSIS will use its defaults.

---

## Build Steps

### Step 1 — Bundle Python scripts into .exe files
```
python build.py
```
This runs PyInstaller for each component and places the results in:
```
dist\ScreenLimiter\
    service.exe
    popup.exe
    tray.exe
    assignments.exe
    settings.exe
```
This takes a few minutes — PyInstaller is packaging the entire Python runtime
and all dependencies into each exe.

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
2. **License page** — displays LICENSE.txt
3. **Directory page** — defaults to `C:\Program Files\ScreenLimiter`
4. **Install page** — copies files, registers service, writes registry
5. **Finish page** — Settings window opens automatically for first-time config

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
    EstimatedSize      = (calculated)

HKCU\SOFTWARE\Microsoft\Windows\CurrentVersion\Run\
    ScreenLimiterTray  = "C:\Program Files\ScreenLimiter\tray.exe"
```

The Windows Service is registered as `ScreenLimiterSvc` with:
- Start type: Automatic (starts at boot)
- Recovery: Restart after 5s / 10s / 30s on failure

---

## Uninstalling

Via **Add/Remove Programs** (Settings → Apps) or by running  
`C:\Program Files\ScreenLimiter\Uninstall.exe`.

The uninstaller stops and removes the service, removes all registry entries,
removes Start Menu shortcuts, and deletes the install directory.

Your personal data (`%APPDATA%\ScreenLimiter\`) is intentionally preserved —
delete that folder manually if you want a completely clean removal.
