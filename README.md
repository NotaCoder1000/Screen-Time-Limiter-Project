# Screen Limiter for Windows 11

A hard-to-bypass app limiter that blocks distracting apps until you:
1. Check off all your daily assignments
2. Have at least one GitHub commit for the day

Weekends are automatically unlocked. The blocker runs as a **background process** launched at logon by Task Scheduler with elevated privileges, so it persists even if you close the tray icon.

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
   - Which apps to block
   - An **admin password** to protect settings

That's it. The enforcer starts immediately and a tray icon appears in the system tray.

---

## GitHub Personal Access Token (optional)

Without a token, the tool checks your **public** GitHub activity (PushEvents). This covers most cases.

With a token (recommended), it also catches commits to **private repos**.

**To create a token:**
1. GitHub → Settings → Developer Settings → Personal Access Tokens → Fine-grained tokens
2. Repository access: "All repositories" or specific ones
3. Permissions: `Contents: Read` is sufficient
4. Copy the token and paste it during setup (or in the Admin tab later)

---

## How It Works

```
You double-click chrome.exe
         ↓
enforcer.exe detects it instantly (WMI event)
         ↓
chrome.exe is SUSPENDED (it can't run anything)
         ↓
Popup window appears with your assignment checklist
         ↓
You tick all assignments → click Confirm
         ↓
GitHub API is checked for a commit today (UTC)
         ↓
Pass ✓ → chrome.exe resumes normally
Fail ✗ → chrome.exe is killed
```

---

## Daily Workflow

- Add today's assignments via **tray icon → Open Screen Limiter**
- Check them off one by one as you complete them
- Push at least one commit to any GitHub repo
- Open your blocked apps normally — the popup will verify and let you through

---

## Tray Icon Colors

| Color | Meaning |
|-------|---------|
| 🟢 Green | Assignments done — apps allowed (GitHub checked on each launch) |
| 🔴 Red | Blocked — assignments incomplete or no commit yet |
| 🔵 Blue | Weekend — everything unlocked |

---

## Settings (password-protected)

Right-click tray → **Open Screen Limiter** to change:
- GitHub username / token
- Blocked app list
- Admin password
- Enable/disable the limiter

---

## Files

| File | Purpose |
|------|---------|
| `enforcer.exe` | Background monitor — detects and intercepts blocked apps |
| `popup.exe` | Interception popup shown when a blocked app launches |
| `tray.exe` | System tray icon |
| `main.exe` | Main UI (assignments, blocked apps, admin settings) |

Config and data are stored in: `%APPDATA%\ScreenLimiter\`

The config directory ACLs are hardened to the current user + SYSTEM on every startup.

> **Developers:** See `BUILDING.md` for instructions on building from source.

---

## Architecture Notes

- `enforcer.exe` is **not** a Windows Service. It is a regular user-mode process started by Task Scheduler (`/SC ONLOGON /RL HIGHEST /IT`). This means it runs in the interactive user session without the SCM 30-second startup timeout.
- The GitHub commit check compares timestamps in **UTC** to match GitHub's API, so the check is correct even near midnight across timezones.
- The GitHub token is encrypted at rest with **Windows DPAPI** (user-scope). Both `enforcer.exe` and `main.exe` run under the same interactive user (via `/IT` Task Scheduler flag and HKCU Run key), so decryption always succeeds.

---

## Bypassing Resistance

The enforcer runs elevated (highest privileges). To stop it you need:
- Admin rights + to know the Task Scheduler task name (`ScreenLimiterMonitor`)
- Or the admin password to disable it via the Screen Limiter UI

This is intentionally harder to bypass than a simple user-space script, but a sufficiently determined future-you could still open Task Scheduler and disable the task. That's a feature — if you're going that far, you know you're cheating yourself.

---

## Uninstall

Open **Settings → Apps** (or **Control Panel → Programs and Features**), find **Screen Limiter**, and click **Uninstall**. The wizard will stop the enforcer and remove the scheduled task automatically.
