"""
enforcer.py — Screen Limiter background monitor.

Runs as a hidden background process (NOT a Windows Service).
Started at logon via Task Scheduler (/SC ONLOGON /RL HIGHEST /IT).

Usage:
    enforcer.exe          — run the monitor (normal/background mode)
    enforcer.exe debug    — run with console output visible
"""

import ctypes
import os
import signal
import subprocess
import sys
import threading
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from shared import ensure_secure_app_dir, load_config, log
from core import is_blocked

import win32api
import win32con
import win32process
import wmi

# ── Path resolution ────────────────────────────────────────────────────────────

def _install_dir() -> str:
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))


ENFORCER_DIR = _install_dir()

if getattr(sys, "frozen", False):
    POPUP_CMD = [os.path.join(ENFORCER_DIR, "popup.exe")]
else:
    _pythonw = sys.executable.replace("python.exe", "pythonw.exe")
    if not os.path.exists(_pythonw):
        _pythonw = sys.executable
    POPUP_CMD = [_pythonw, os.path.join(ENFORCER_DIR, "popup.py")]

# ── TTL-based "recently handled" tracker ──────────────────────────────────────
# Replaces the old set + threading.Timer pattern.
# A dict {pid: timestamp} is cheaper to reason about than a timer per pid.

_handled_at: dict[int, float] = {}
_HANDLE_TTL = 5.0          # seconds before a pid is eligible for re-handling
_lock = threading.Lock()
_stop_event = threading.Event()


def _is_recently_handled(pid: int) -> bool:
    """Return True if pid was handled within the last _HANDLE_TTL seconds."""
    t = _handled_at.get(pid)
    if t is None:
        return False
    if time.monotonic() - t > _HANDLE_TTL:
        _handled_at.pop(pid, None)
        return False
    return True


def _mark_handled(pid: int) -> None:
    """Record pid as handled and prune stale entries opportunistically."""
    now = time.monotonic()
    _handled_at[pid] = now
    stale = [p for p, ts in list(_handled_at.items()) if now - ts > _HANDLE_TTL]
    for p in stale:
        _handled_at.pop(p, None)


# ── Low-level process control ──────────────────────────────────────────────────

def suspend_process(pid: int) -> bool:
    try:
        handle = win32api.OpenProcess(
            win32con.PROCESS_SUSPEND_RESUME | win32con.PROCESS_QUERY_INFORMATION,
            False, pid,
        )
        result = ctypes.windll.ntdll.NtSuspendProcess(int(handle))
        win32api.CloseHandle(handle)
        return result == 0
    except Exception as e:
        log(f"suspend_process({pid}) failed: {e}", level="error")
        return False


def resume_process(pid: int) -> bool:
    try:
        handle = win32api.OpenProcess(win32con.PROCESS_SUSPEND_RESUME, False, pid)
        result = ctypes.windll.ntdll.NtResumeProcess(int(handle))
        win32api.CloseHandle(handle)
        return result == 0
    except Exception as e:
        log(f"resume_process({pid}) failed: {e}", level="error")
        return False


def kill_process(pid: int) -> None:
    try:
        handle = win32api.OpenProcess(win32con.PROCESS_TERMINATE, False, pid)
        win32process.TerminateProcess(handle, 1)
        win32api.CloseHandle(handle)
        log(f"Killed pid {pid}")
    except Exception as e:
        log(f"kill_process({pid}) failed: {e}", level="error")


# ── Intercept logic ────────────────────────────────────────────────────────────

def handle_blocked_launch(pid: int, app_name: str) -> None:
    """
    Suspend the process, show the popup, then resume or kill based on the result.

    The try/finally guarantees the process is never left suspended:
      - if popup says "allow" → resume
      - if popup says "deny", times out, or crashes → kill
      - if an unexpected exception occurs before the decision → kill (fail-safe)
    """
    with _lock:
        if _is_recently_handled(pid):
            return
        _mark_handled(pid)

    log(f"Intercepted: {app_name} (pid {pid})")
    time.sleep(0.3)  # Brief pause so the process window can initialise

    suspended = suspend_process(pid)
    if not suspended:
        log(f"Could not suspend {pid} ({app_name}) — likely a privileged process, skipping.")
        with _lock:
            _handled_at.pop(pid, None)
        return

    allowed = False
    try:
        try:
            result = subprocess.run(POPUP_CMD + [str(pid), app_name], timeout=300)
            allowed = (result.returncode == 0)
            log(f"Popup result for {app_name} (pid {pid}): {'ALLOW' if allowed else 'DENY'}")
        except subprocess.TimeoutExpired:
            log(f"Popup timed out for {app_name} (pid {pid}) — denying.")
        except Exception as e:
            log(f"Popup launch error for {app_name} (pid {pid}): {e}", level="error")
    finally:
        # This block always runs — process is never left suspended.
        if allowed:
            log(f"Resuming {app_name} (pid {pid})")
            resume_process(pid)
        else:
            log(f"Killing {app_name} (pid {pid})")
            kill_process(pid)


def _check_event(process_name: str, pid: int) -> None:
    if not process_name:
        return
    cfg = load_config()
    if is_blocked(process_name, cfg):
        threading.Thread(
            target=handle_blocked_launch,
            args=(pid, process_name),
            daemon=True,
        ).start()


def check_running_blocked() -> None:
    """
    Scan running processes and handle any that are on the blocked list.
    Called once at startup and then every 30 s via _periodic_check_loop().
    """
    try:
        import psutil
        cfg = load_config()
        blocked = {b.lower() for b in cfg.get("blocked_apps", [])}
        if not blocked:
            return
        from core import should_enforce
        if not should_enforce(cfg):
            return

        for proc in psutil.process_iter(["pid", "name"]):
            try:
                name = (proc.info["name"] or "").lower()
                pid = proc.pid
                if name in blocked:
                    with _lock:
                        already = _is_recently_handled(pid)
                    if not already:
                        log(f"Already-running blocked process: {name} (pid {pid})")
                        threading.Thread(
                            target=handle_blocked_launch,
                            args=(pid, proc.info["name"]),
                            daemon=True,
                        ).start()
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                pass
    except ImportError:
        pass


def _periodic_check_loop() -> None:
    """Re-scan every 30 s to catch apps that were opened while the limiter was disabled."""
    while not _stop_event.is_set():
        time.sleep(30)
        check_running_blocked()


# ── Monitor loop ───────────────────────────────────────────────────────────────

def run_monitor() -> None:
    try:
        c = wmi.WMI()
        watcher = c.Win32_ProcessStartTrace.watch_for("creation")
        log("WMI process watcher active.")
    except Exception as e:
        log(f"WMI watcher failed: {e} — switching to polling fallback.")
        run_polling()
        return

    while not _stop_event.is_set():
        try:
            try:
                event = watcher(timeout_ms=500)
                _check_event(event.ProcessName, event.ProcessId)
            except wmi.x_wmi_timed_out:
                pass
        except Exception as e:
            log(f"WMI error: {e}", level="warning")
            time.sleep(2)


def run_polling() -> None:
    import psutil
    seen_pids = {p.pid for p in psutil.process_iter()}
    log("Polling fallback active.")
    while not _stop_event.is_set():
        time.sleep(1)
        try:
            for proc in psutil.process_iter(["pid", "name"]):
                if proc.pid not in seen_pids:
                    seen_pids.add(proc.pid)
                    _check_event(proc.info["name"], proc.pid)
            alive = {p.pid for p in psutil.process_iter()}
            seen_pids &= alive
        except Exception as e:
            log(f"Polling error: {e}", level="warning")


# ── Entry point ────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    debug = len(sys.argv) > 1 and sys.argv[1].lower() == "debug"

    if not debug and getattr(sys, "frozen", False):
        ctypes.windll.user32.ShowWindow(ctypes.windll.kernel32.GetConsoleWindow(), 0)

    log(f"Screen Limiter enforcer starting ({'debug' if debug else 'background'} mode).")

    # Harden config directory ACLs on every startup (idempotent).
    ensure_secure_app_dir()

    def _handle_signal(sig, frame):
        log("Enforcer shutting down.")
        _stop_event.set()

    signal.signal(signal.SIGTERM, _handle_signal)
    signal.signal(signal.SIGINT, _handle_signal)

    # Handle blocked apps that were already running before the enforcer started.
    check_running_blocked()

    # Periodic scan: catches apps opened while the limiter was disabled.
    threading.Thread(target=_periodic_check_loop, daemon=True).start()

    try:
        run_monitor()
    except Exception as e:
        log(f"Enforcer crashed: {e}", level="error")

    log("Enforcer exited.")
