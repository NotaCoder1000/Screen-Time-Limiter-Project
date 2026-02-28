# Screen Limiter for Windows 11

A hard-to-bypass app limiter that blocks distracting apps until you:
1. Check off all your daily assignments
2. Have at least one GitHub commit for the day

Weekends are automatically unlocked. The blocker runs as a **Windows Service** so it persists even if you close the tray icon.

---

## Requirements

- Windows 10/11
- A GitHub account

---

## Installation

1. **Download `ScreenLimiter-Setup.exe`** from the [Releases](../../releases) page
2. **Right-click → Run as administrator**
3. Follow the installer wizard — once it finishes, the first-run setup window opens automatically and asks for:
   - Your GitHub username
   - A GitHub Personal Access Token *(optional, but enables private repo commit detection)*
   - Which apps to block (enter `.exe` names — find them in Task Manager → Details tab)
   - An **admin password** to protect settings

That's it. The service starts immediately and a tray icon appears in the system tray.

---

## GitHub Personal Access Token (optional)

Without a token, the tool checks your **public** GitHub activity (PushEvents). This covers most cases.

With a token (recommended), it also catches commits to **private repos**.

**To create a token:**
1. GitHub → Settings → Developer Settings → Personal Access Tokens → Fine-grained tokens
2. Repository access: "All repositories" or specific ones
3. Permissions: `Contents: Read` is sufficient
4. Copy the token and paste it during setup (or in Settings later)

---

## How It Works

```
You double-click chrome.exe
         ↓
Windows Service detects it instantly (WMI event)
         ↓
example.exe is SUSPENDED (it can't run anything)
         ↓
Popup window appears with your assignment checklist
         ↓
You tick all assignments → click Confirm
         ↓
GitHub API is checked for a commit today
         ↓
Pass ✓ → example.exe resumes normally
Fail ✗ → example.exe is killed
```

---

## Daily Workflow

- Add today's assignments via **tray icon → Manage Assignments**
- Check them off one by one as you complete them
- Push at least one commit to any GitHub repo
- Open your blocked apps normally — the popup will verify and let you through
- Assignments auto-reset at midnight each day

---

## Tray Icon Colors

| Color | Meaning |
|-------|---------|
| 🟢 Green | Assignments done — apps allowed (GitHub checked on each launch) |
| 🔴 Red | Blocked — assignments incomplete or no commit yet |
| 🔵 Blue | Weekend — everything unlocked |

---

## Settings (password-protected)

Right-click tray → **Settings** to change:
- GitHub username / token
- Blocked app list
- Admin password
- Enable/disable the limiter

---

## Files

| File | Purpose |
|------|---------|
| `service.exe` | Windows Service — the core enforcer |
| `popup.exe` | Interception popup shown when blocked app launches |
| `tray.exe` | System tray icon |
| `main.exe` | Main UI (assignments, blocked apps, admin settings) |

Config and data are stored in: `%APPDATA%\ScreenLimiter\`

> **Developers:** See `BUILDING.md` for instructions on building from source.

---

## Bypassing Resistance

The service runs under **LocalSystem** privileges. To stop it you need:
- Admin rights + to know it's called `ScreenLimiterSvc`
- Or the admin password to disable it via Settings

This is intentionally harder to bypass than a simple user-space script, but determined future-you could still open Task Manager as admin and stop the service. That's a feature — if you're going that far, you know you're cheating yourself.

---

## Uninstall

Open **Settings → Apps** (or **Control Panel → Programs and Features**), find **Screen Limiter**, and click **Uninstall**. The wizard will stop and remove the service automatically.
