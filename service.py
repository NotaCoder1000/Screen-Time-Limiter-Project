"""
service.py - Screen Limiter background monitor.

Runs as a hidden background process (not a Windows Service).
Started automatically at login via the registry Run key.
Kept alive by the Task Scheduler as a fallback.

Usage:
    service.exe          - run the monitor (normal mode)
    service.exe debug    - run with console output
"""

import sys
import os
import time
import subprocess
import datetime
import ctypes
import threading
import signal

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from shared import load_config, log

import win32con
import win32process
import win32api
import wmi

# ── Path resolution ────────────────────────────────────────────────────────────
def _install_dir() -> str:
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))

SERVICE_DIR = _install_dir()

if getattr(sys, "frozen", False):
    POPUP_CMD = [os.path.join(SERVICE_DIR, "popup.exe")]
else:
    _pythonw = sys.executable.replace("python.exe", "pythonw.exe")
    if not os.path.exists(_pythonw):
        _pythonw = sys.executable
    POPUP_CMD = [_pythonw, os.path.join(SERVICE_DIR, "popup.py")]

# ── Process management ─────────────────────────────────────────────────────────
_recently_handled = set()
_lock = threading.Lock()
_stop_event = threading.Event()

def suspend_process(pid: int) -> bool:
    try:
        handle = win32api.OpenProcess(
            win32con.PROCESS_SUSPEND_RESUME | win32con.PROCESS_QUERY_INFORMATION,
            False, pid
        )
        result = ctypes.windll.ntdll.NtSuspendProcess(int(handle))
        win32api.CloseHandle(handle)
        return result == 0
    except Exception as e:
        log(f"suspend_process({pid}) failed: {e}")
        return False

def resume_process(pid: int) -> bool:
    try:
        handle = win32api.OpenProcess(win32con.PROCESS_SUSPEND_RESUME, False, pid)
        result = ctypes.windll.ntdll.NtResumeProcess(int(handle))
        win32api.CloseHandle(handle)
        return result == 0
    except Exception as e:
        log(f"resume_process({pid}) failed: {e}")
        return False

def kill_process(pid: int):
    try:
        handle = win32api.OpenProcess(win32con.PROCESS_TERMINATE, False, pid)
        win32process.TerminateProcess(handle, 1)
        win32api.CloseHandle(handle)
        log(f"Killed pid {pid}")
    except Exception as e:
        log(f"kill_process({pid}) failed: {e}")

def handle_blocked_launch(pid: int, app_name: str):
    with _lock:
        if pid in _recently_handled:
            return
        _recently_handled.add(pid)

    log(f"Intercepted: {app_name} (pid {pid})")
    time.sleep(0.3)

    suspended = suspend_process(pid)
    if not suspended:
        log(f"Could not suspend {pid} ({app_name}) — privileged helper, skipping.")
        _recently_handled.discard(pid)
        return

    try:
        result = subprocess.run(POPUP_CMD + [str(pid), app_name], timeout=300)
        allowed = (result.returncode == 0)
    except subprocess.TimeoutExpired:
        allowed = False
        log(f"Popup timed out for {app_name} — denying.")
    except Exception as e:
        log(f"Popup launch error: {e}")
        allowed = False

    if allowed:
        log(f"Resuming {app_name} (pid {pid})")
        resume_process(pid)
    else:
        log(f"Killing {app_name} (pid {pid})")
        kill_process(pid)

    threading.Timer(5.0, lambda: _recently_handled.discard(pid)).start()

def is_weekend() -> bool:
    return datetime.date.today().weekday() >= 5

def _check_event(process_name: str, pid: int):
    if not process_name:
        return
    cfg = load_config()
    if not cfg.get("enabled", True):
        return
    if is_weekend():
        return
    blocked = [b.lower() for b in cfg.get("blocked_apps", [])]
    if process_name.lower() in blocked:
        threading.Thread(
            target=handle_blocked_launch,
            args=(pid, process_name),
            daemon=True
        ).start()

def check_running_blocked():
    """
    Scan all currently-running processes and handle any that are on the
    blocked list. Called once at startup and then every 30 seconds so that
    apps which were already open when the limiter was (re-)enabled get caught.
    """
    try:
        import psutil
        cfg = load_config()
        if not cfg.get("enabled", True):
            return
        if is_weekend():
            return
        blocked = [b.lower() for b in cfg.get("blocked_apps", [])]
        if not blocked:
            return

        for proc in psutil.process_iter(["pid", "name"]):
            try:
                name = (proc.info["name"] or "").lower()
                pid  = proc.pid
                if name in blocked:
                    with _lock:
                        already = pid in _recently_handled
                    if not already:
                        log(f"Already-running blocked process found: {name} (pid {pid})")
                        threading.Thread(
                            target=handle_blocked_launch,
                            args=(pid, proc.info["name"]),
                            daemon=True,
                        ).start()
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                pass
    except ImportError:
        pass

def _periodic_check_loop():
    """Re-check every 30 s so apps opened while the limiter was disabled get caught."""
    while not _stop_event.is_set():
        time.sleep(30)
        check_running_blocked()

# ── Monitor loop ───────────────────────────────────────────────────────────────
def run_monitor():
    try:
        c = wmi.WMI()
        watcher = c.Win32_ProcessStartTrace.watch_for("creation")
        log("WMI process watcher active.")
    except Exception as e:
        log(f"WMI watcher failed: {e}. Using polling fallback.")
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
            log(f"WMI error: {e}")
            time.sleep(2)

def run_polling():
    import psutil
    seen_pids = set(p.pid for p in psutil.process_iter())
    log("Polling fallback active.")
    while not _stop_event.is_set():
        time.sleep(1)
        try:
            for proc in psutil.process_iter(["pid", "name"]):
                if proc.pid not in seen_pids:
                    seen_pids.add(proc.pid)
                    _check_event(proc.info["name"], proc.pid)
            alive = set(p.pid for p in psutil.process_iter())
            seen_pids &= alive
        except Exception as e:
            log(f"Polling error: {e}")

# ── Entry point ────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    debug = len(sys.argv) > 1 and sys.argv[1].lower() == "debug"

    if not debug and getattr(sys, "frozen", False):
        # Hide the console window when running as a background process
        ctypes.windll.user32.ShowWindow(ctypes.windll.kernel32.GetConsoleWindow(), 0)

    log(f"Screen Limiter monitor starting ({'debug' if debug else 'background'} mode).")

    def _handle_signal(sig, frame):
        log("Monitor shutting down.")
        _stop_event.set()

    signal.signal(signal.SIGTERM, _handle_signal)
    signal.signal(signal.SIGINT, _handle_signal)

    # Kill any blocked apps that were already running before the monitor started
    check_running_blocked()

    # Periodic scan: catches apps opened while the limiter was disabled
    threading.Thread(target=_periodic_check_loop, daemon=True).start()

    try:
        run_monitor()
    except Exception as e:
        log(f"Monitor crashed: {e}")

    log("Monitor exited.")
