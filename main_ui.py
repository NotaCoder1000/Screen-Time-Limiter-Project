"""
main_ui.py — Combined Screen Limiter control panel.

Tabs:
  1. Assignments  — manage daily tasks (no password required)
  2. Blocked Apps — add apps freely; removing apps requires a password
  3. Admin        — GitHub credentials, admin password (password-gated tab)

Limiter toggle (header):
  - Enable limiter:  no password required
  - Disable limiter: password required
"""

import sys
import os
import re
import uuid
import glob
import threading
import tkinter as tk
import customtkinter as ctk
import winreg

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from shared import (
    load_config, save_config,
    load_assignments, save_assignments,
    hash_password, check_password, log,
    encrypt_token, decrypt_token,
)

ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")

ACCENT  = "#3b82f6"
RED     = "#ef4444"
GREEN   = "#22c55e"
YELLOW  = "#f59e0b"
BG      = "#0f172a"
CARD    = "#1e293b"
CARD2   = "#273449"
TEXT    = "#f1f5f9"
SUBTEXT = "#94a3b8"
BORDER  = "#334155"


# ── App scanning ────────────────────────────────────────────────────────────────

def _exes_from_registry() -> dict:
    results = {}
    keys = [
        (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall"),
        (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall"),
        (winreg.HKEY_CURRENT_USER,  r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall"),
    ]
    for hive, path in keys:
        try:
            root = winreg.OpenKey(hive, path)
        except OSError:
            continue
        i = 0
        while True:
            try:
                subkey_name = winreg.EnumKey(root, i)
                i += 1
            except OSError:
                break
            try:
                sub = winreg.OpenKey(root, subkey_name)
            except OSError:
                continue
            try:
                display_name, _ = winreg.QueryValueEx(sub, "DisplayName")
            except OSError:
                winreg.CloseKey(sub)
                continue

            exe_name = None
            for val in ("DisplayIcon", "InstallLocation"):
                try:
                    raw, _ = winreg.QueryValueEx(sub, val)
                    raw = raw.strip().strip('"').split(",")[0].split(" /")[0].strip()
                    if raw.lower().endswith(".exe") and os.path.exists(raw):
                        exe_name = os.path.basename(raw).lower()
                        break
                    if val == "InstallLocation" and os.path.isdir(raw):
                        for f in glob.glob(os.path.join(raw, "*.exe")):
                            candidate = os.path.basename(f).lower()
                            if not any(x in candidate for x in ("unins", "update", "helper", "crash", "setup")):
                                exe_name = candidate
                                break
                except OSError:
                    pass

            if exe_name:
                clean_name = re.sub(r"\s+\d[\d.]+$", "", str(display_name)).strip()
                results[exe_name] = clean_name
            winreg.CloseKey(sub)
        winreg.CloseKey(root)
    return results


def _exes_from_program_files() -> dict:
    results = {}
    roots = [
        os.environ.get("PROGRAMFILES",     r"C:\Program Files"),
        os.environ.get("PROGRAMFILES(X86)", r"C:\Program Files (x86)"),
        os.path.join(os.environ.get("LOCALAPPDATA", ""), "Programs"),
    ]
    skip_fragments = ("unins", "update", "helper", "crash", "setup", "install",
                      "repair", "redist", "vcredist", "dotnet", "runtime")
    for root in roots:
        if not root or not os.path.isdir(root):
            continue
        for vendor_dir in os.scandir(root):
            if not vendor_dir.is_dir():
                continue
            try:
                for entry in os.scandir(vendor_dir.path):
                    if entry.is_file() and entry.name.lower().endswith(".exe"):
                        exe = entry.name.lower()
                        if not any(s in exe for s in skip_fragments):
                            results.setdefault(exe, vendor_dir.name)
            except PermissionError:
                pass
    return results


def _exes_from_running_processes() -> dict:
    results = {}
    try:
        import psutil
        system_names = {
            "system", "system idle process", "registry", "smss.exe",
            "csrss.exe", "wininit.exe", "services.exe", "lsass.exe",
            "svchost.exe", "dwm.exe", "conhost.exe",
        }
        for proc in psutil.process_iter(["name"]):
            try:
                name = (proc.info["name"] or "").lower()
                if name and name.endswith(".exe") and name not in system_names:
                    label = name.replace(".exe", "").replace("-", " ").replace("_", " ").title()
                    results.setdefault(name, label)
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                pass
    except ImportError:
        pass
    return results


def _exes_from_roblox() -> dict:
    """
    Roblox installs to %LOCALAPPDATA%\\Roblox\\Versions\\version-xxx\\
    which is not in Program Files and not in the standard registry uninstall keys.
    Scans all version subdirectories for known Roblox executables.
    """
    results = {}
    roblox_base = os.path.join(os.environ.get("LOCALAPPDATA", ""), "Roblox", "Versions")
    if not os.path.isdir(roblox_base):
        return results

    # Known Roblox exe filenames → friendly display names
    targets = {
        "robloxplayerbeta.exe":    "Roblox Player",
        "robloxstudiobeta.exe":    "Roblox Studio",
        "robloxplayer.exe":        "Roblox Player",
        "robloxstudio.exe":        "Roblox Studio",
        "robloxplayerlauncher.exe": "Roblox Launcher",
    }
    try:
        for version_dir in os.scandir(roblox_base):
            if not version_dir.is_dir():
                continue
            try:
                for entry in os.scandir(version_dir.path):
                    key = entry.name.lower()
                    if key in targets:
                        results[key] = targets[key]
            except PermissionError:
                pass
    except PermissionError:
        pass
    return results


def scan_installed_apps() -> list:
    """Combine all sources and return a sorted list of (exe_name, display_name)."""
    combined: dict = {}
    # Lower-priority sources first so registry names win
    combined.update(_exes_from_program_files())
    combined.update(_exes_from_running_processes())
    combined.update(_exes_from_roblox())    # before registry so registry display names win if present
    combined.update(_exes_from_registry())  # highest priority for display names

    skip = ("unins", "update", "helper", "crash", "setup", "install",
            "repair", "redist", "vcredist", "dotnet", "runtime", "msiexec",
            "dllhost", "rundll", "regsvr", "werfault", "watson")
    filtered = {
        exe: name for exe, name in combined.items()
        if not any(s in exe for s in skip)
    }
    return sorted(filtered.items(), key=lambda x: x[1].lower())


# ── Reusable password dialog ────────────────────────────────────────────────────

class PasswordDialog(ctk.CTkToplevel):
    """
    Modal password prompt.
    Calls on_success() if the password is correct (or no password is set).
    Calls on_fail() if the user cancels.
    """

    def __init__(self, parent, prompt="Enter admin password:",
                 on_success=None, on_fail=None):
        super().__init__(parent)
        self._on_success = on_success or (lambda: None)
        self._on_fail    = on_fail    or (lambda: None)
        self.title("Admin Authentication")
        self.geometry("360x220")
        self.resizable(False, False)
        self.configure(fg_color=BG)
        self.attributes("-topmost", True)
        self.grab_set()
        self.protocol("WM_DELETE_WINDOW", self._cancel)

        ctk.CTkLabel(
            self, text=f"🔒  {prompt}",
            font=ctk.CTkFont(size=13, weight="bold"), text_color=TEXT,
            wraplength=320,
        ).pack(pady=(26, 8), padx=20)

        self.pw_entry = ctk.CTkEntry(
            self, show="●", width=280, height=42,
            fg_color=CARD, border_color=BORDER, text_color=TEXT,
            font=ctk.CTkFont(size=13),
        )
        self.pw_entry.pack(pady=(0, 6))
        self.pw_entry.bind("<Return>", lambda _: self._submit())
        self.pw_entry.focus()

        self.err_label = ctk.CTkLabel(
            self, text="", font=ctk.CTkFont(size=11), text_color=RED
        )
        self.err_label.pack()

        btn_row = ctk.CTkFrame(self, fg_color="transparent")
        btn_row.pack(pady=(8, 0))
        ctk.CTkButton(
            btn_row, text="Unlock", fg_color=ACCENT, hover_color="#2563eb",
            height=40, width=130, font=ctk.CTkFont(size=13, weight="bold"),
            command=self._submit,
        ).pack(side="left", padx=(0, 8))
        ctk.CTkButton(
            btn_row, text="Cancel",
            fg_color="transparent", border_color=BORDER, border_width=1,
            text_color=SUBTEXT, hover_color=CARD2,
            height=40, width=130, command=self._cancel,
        ).pack(side="left")

    def _submit(self):
        cfg    = load_config()
        hashed = cfg.get("password_hash", "")
        pw     = self.pw_entry.get()
        if not hashed or check_password(pw, hashed):
            self.destroy()
            self._on_success()
        else:
            self.err_label.configure(text="Incorrect password.")
            self.pw_entry.delete(0, "end")

    def _cancel(self):
        self.destroy()
        self._on_fail()


# ── Main application window ─────────────────────────────────────────────────────

class ScreenLimiterApp(ctk.CTk):

    def __init__(self, firstrun: bool = False):
        super().__init__()
        self.title("Screen Limiter")
        self.geometry("740x840")
        self.minsize(680, 700)
        self.configure(fg_color=BG)
        self.attributes("-topmost", True)
        self.lift()

        self._firstrun        = firstrun
        # Admin tab stays unlocked for the session once entered.
        # On firstrun (no password set) we skip the gate.
        self._admin_unlocked  = firstrun
        self._last_tab        = "Assignments"

        # Blocked apps scan state
        self._app_rows: list  = []          # (exe, display_name, BooleanVar)
        self._initially_blocked: set = set()
        self._scan_status_var = tk.StringVar(value="Scanning installed apps…")

        self._build_ui()

    # ── UI construction ────────────────────────────────────────────────────────

    def _build_ui(self):
        cfg = load_config()
        self._build_header(cfg)

        self.tabview = ctk.CTkTabview(
            self,
            fg_color=CARD,
            segmented_button_fg_color=CARD2,
            segmented_button_selected_color=ACCENT,
            segmented_button_selected_hover_color="#2563eb",
            segmented_button_unselected_color=CARD2,
            segmented_button_unselected_hover_color=BORDER,
            command=self._on_tab_change,
        )
        self.tabview.pack(fill="both", expand=True, padx=16, pady=(0, 16))

        self.tabview.add("Assignments")
        self.tabview.add("Blocked Apps")
        self.tabview.add("Admin")

        self._build_assignments_tab(self.tabview.tab("Assignments"))
        self._build_blocked_apps_tab(self.tabview.tab("Blocked Apps"), cfg)
        self._build_admin_tab(self.tabview.tab("Admin"), cfg)

        threading.Thread(target=self._scan_apps_thread, args=(cfg,), daemon=True).start()

    # ── Header ─────────────────────────────────────────────────────────────────

    def _build_header(self, cfg):
        hdr = ctk.CTkFrame(self, fg_color=CARD, corner_radius=0, height=72)
        hdr.pack(fill="x")
        hdr.pack_propagate(False)

        ctk.CTkLabel(
            hdr, text="🛡  Screen Limiter",
            font=ctk.CTkFont(size=18, weight="bold"), text_color=TEXT,
        ).pack(side="left", padx=20)

        right = ctk.CTkFrame(hdr, fg_color="transparent")
        right.pack(side="right", padx=20)

        enabled = cfg.get("enabled", True)
        self.status_badge = ctk.CTkLabel(
            right,
            text="● ACTIVE" if enabled else "○ DISABLED",
            font=ctk.CTkFont(size=12, weight="bold"),
            text_color=GREEN if enabled else RED,
        )
        self.status_badge.pack(side="left", padx=(0, 14))

        self.toggle_btn = ctk.CTkButton(
            right,
            text="Disable Limiter" if enabled else "Enable Limiter",
            font=ctk.CTkFont(size=12, weight="bold"),
            fg_color=RED if enabled else GREEN,
            hover_color="#b91c1c" if enabled else "#16a34a",
            height=36, width=148,
            command=self._on_toggle_limiter,
        )
        self.toggle_btn.pack(side="left")

    def _on_toggle_limiter(self):
        cfg = load_config()
        if cfg.get("enabled", True):
            # Disabling requires password
            PasswordDialog(
                self,
                prompt="Enter password to disable the limiter:",
                on_success=self._disable_limiter,
            )
        else:
            # Enabling: no password needed
            self._enable_limiter()

    def _enable_limiter(self):
        cfg = load_config()
        cfg["enabled"] = True
        save_config(cfg)
        log("Limiter enabled via GUI.")
        self._update_header(enabled=True)

    def _disable_limiter(self):
        cfg = load_config()
        cfg["enabled"] = False
        save_config(cfg)
        log("Limiter disabled via GUI.")
        self._update_header(enabled=False)

    def _update_header(self, enabled: bool):
        self.status_badge.configure(
            text="● ACTIVE" if enabled else "○ DISABLED",
            text_color=GREEN if enabled else RED,
        )
        self.toggle_btn.configure(
            text="Disable Limiter" if enabled else "Enable Limiter",
            fg_color=RED if enabled else GREEN,
            hover_color="#b91c1c" if enabled else "#16a34a",
        )

    # ── Tab change / Admin gate ─────────────────────────────────────────────────

    def _on_tab_change(self):
        current = self.tabview.get()
        if current == "Admin" and not self._admin_unlocked:
            # Switch back before showing the dialog to avoid a visual flash
            self.tabview.set(self._last_tab)
            PasswordDialog(
                self,
                prompt="Enter admin password to access Admin settings:",
                on_success=self._open_admin_tab,
            )
        else:
            if current != "Admin":
                self._last_tab = current

    def _open_admin_tab(self):
        self._admin_unlocked = True
        self.tabview.set("Admin")

    # ── Assignments Tab ─────────────────────────────────────────────────────────

    def _build_assignments_tab(self, tab):
        # Add new assignment row
        add_row = ctk.CTkFrame(tab, fg_color="transparent")
        add_row.pack(fill="x", padx=4, pady=(12, 8))

        self.new_entry = ctk.CTkEntry(
            add_row,
            placeholder_text="e.g. Chapter 5 reading, Problem set 3…",
            font=ctk.CTkFont(size=13), height=40,
            fg_color=BG, border_color=BORDER, text_color=TEXT,
        )
        self.new_entry.pack(side="left", fill="x", expand=True, padx=(0, 8))
        self.new_entry.bind("<Return>", lambda _: self._add_assignment())

        ctk.CTkButton(
            add_row, text="+ Add",
            font=ctk.CTkFont(size=13, weight="bold"),
            fg_color=ACCENT, hover_color="#2563eb",
            width=80, height=40, command=self._add_assignment,
        ).pack(side="left")

        # Divider + list header
        ctk.CTkFrame(tab, fg_color=BORDER, height=1).pack(fill="x", padx=4, pady=(4, 0))

        list_hdr = ctk.CTkFrame(tab, fg_color="transparent")
        list_hdr.pack(fill="x", padx=4, pady=(8, 4))
        ctk.CTkLabel(
            list_hdr, text="Today's Assignments",
            font=ctk.CTkFont(size=13, weight="bold"), text_color=TEXT,
        ).pack(side="left")
        self.assign_count_lbl = ctk.CTkLabel(
            list_hdr, text="", font=ctk.CTkFont(size=11), text_color=SUBTEXT,
        )
        self.assign_count_lbl.pack(side="right")

        # Scrollable list
        self.assign_list = ctk.CTkScrollableFrame(
            tab, fg_color=BG, corner_radius=10,
        )
        self.assign_list.pack(fill="both", expand=True, padx=4, pady=(0, 8))

        # Bottom buttons
        btn_row = ctk.CTkFrame(tab, fg_color="transparent")
        btn_row.pack(fill="x", padx=4, pady=(0, 10))

        ctk.CTkButton(
            btn_row, text="✓  Mark All Done",
            font=ctk.CTkFont(size=12), fg_color=GREEN, hover_color="#16a34a",
            height=36, command=self._mark_all_done,
        ).pack(side="left", padx=(0, 8))
        ctk.CTkButton(
            btn_row, text="↺  Reset All",
            font=ctk.CTkFont(size=12), fg_color="transparent",
            hover_color=CARD2, border_color=BORDER, border_width=1,
            text_color=SUBTEXT, height=36, command=self._reset_all,
        ).pack(side="left", padx=(0, 8))
        ctk.CTkButton(
            btn_row, text="🗑  Clear Completed",
            font=ctk.CTkFont(size=12), fg_color="transparent",
            hover_color=CARD2, border_color=BORDER, border_width=1,
            text_color=SUBTEXT, height=36, command=self._clear_completed,
        ).pack(side="left")

        self._refresh_assignments()

    def _refresh_assignments(self):
        for w in self.assign_list.winfo_children():
            w.destroy()

        assignments = load_assignments()
        done_count  = sum(1 for a in assignments if a.get("done"))
        total       = len(assignments)
        self.assign_count_lbl.configure(text=f"{done_count}/{total} done")

        if not assignments:
            ctk.CTkLabel(
                self.assign_list,
                text="No assignments yet. Add one above!",
                font=ctk.CTkFont(size=13), text_color=SUBTEXT,
            ).pack(pady=32)
            return

        for a in assignments:
            row = ctk.CTkFrame(self.assign_list, fg_color=CARD, corner_radius=8)
            row.pack(fill="x", pady=3, padx=4)
            var = tk.BooleanVar(value=a.get("done", False))
            ctk.CTkCheckBox(
                row, text=a["text"], variable=var,
                font=ctk.CTkFont(size=13),
                text_color=SUBTEXT if a.get("done") else TEXT,
                fg_color=ACCENT, hover_color="#2563eb", checkmark_color="white",
                command=lambda assignment=a, v=var: self._toggle_assignment(assignment, v),
            ).pack(side="left", padx=12, pady=10)
            ctk.CTkButton(
                row, text="✕", width=28, height=28,
                fg_color="transparent", hover_color=RED,
                text_color=SUBTEXT, font=ctk.CTkFont(size=11, weight="bold"),
                command=lambda assignment=a: self._delete_assignment(assignment),
            ).pack(side="right", padx=8)

    def _add_assignment(self):
        text = self.new_entry.get().strip()
        if not text:
            return
        assignments = load_assignments()
        assignments.append({"id": str(uuid.uuid4()), "text": text, "done": False})
        save_assignments(assignments)
        self.new_entry.delete(0, "end")
        self._refresh_assignments()

    def _toggle_assignment(self, assignment: dict, var: tk.BooleanVar):
        assignments = load_assignments()
        for a in assignments:
            if a["id"] == assignment["id"]:
                a["done"] = var.get()
        save_assignments(assignments)
        self._refresh_assignments()

    def _delete_assignment(self, assignment: dict):
        assignments = [a for a in load_assignments() if a["id"] != assignment["id"]]
        save_assignments(assignments)
        self._refresh_assignments()

    def _mark_all_done(self):
        assignments = load_assignments()
        for a in assignments:
            a["done"] = True
        save_assignments(assignments)
        self._refresh_assignments()

    def _reset_all(self):
        assignments = load_assignments()
        for a in assignments:
            a["done"] = False
        save_assignments(assignments)
        self._refresh_assignments()

    def _clear_completed(self):
        assignments = [a for a in load_assignments() if not a.get("done")]
        save_assignments(assignments)
        self._refresh_assignments()

    # ── Blocked Apps Tab ────────────────────────────────────────────────────────

    def _build_blocked_apps_tab(self, tab, cfg):
        self._initially_blocked = set(cfg.get("blocked_apps", []))

        ctk.CTkLabel(
            tab,
            text="Check apps below to block them. Unchecking a currently-blocked app requires a password.",
            font=ctk.CTkFont(size=11), text_color=SUBTEXT, wraplength=680,
        ).pack(anchor="w", padx=4, pady=(8, 6))

        # Search + counter
        search_row = ctk.CTkFrame(tab, fg_color="transparent")
        search_row.pack(fill="x", padx=4, pady=(0, 6))

        self.search_var = tk.StringVar()
        self.search_var.trace_add("write", lambda *_: self._filter_apps())
        ctk.CTkEntry(
            search_row, textvariable=self.search_var,
            placeholder_text="🔍  Search apps…",
            height=36, fg_color=BG, border_color=BORDER,
            text_color=TEXT, font=ctk.CTkFont(size=13),
        ).pack(side="left", fill="x", expand=True, padx=(0, 10))

        self.blocked_count_lbl = ctk.CTkLabel(
            search_row, text="", font=ctk.CTkFont(size=12), text_color=SUBTEXT,
        )
        self.blocked_count_lbl.pack(side="right")

        # Select all / deselect all
        btn_row = ctk.CTkFrame(tab, fg_color="transparent")
        btn_row.pack(fill="x", padx=4, pady=(0, 4))
        ctk.CTkButton(
            btn_row, text="Select All Visible", width=140, height=28,
            fg_color="transparent", border_color=BORDER, border_width=1,
            text_color=SUBTEXT, hover_color=CARD2, font=ctk.CTkFont(size=11),
            command=self._select_all_visible,
        ).pack(side="left", padx=(0, 8))
        ctk.CTkButton(
            btn_row, text="Deselect All", width=110, height=28,
            fg_color="transparent", border_color=BORDER, border_width=1,
            text_color=SUBTEXT, hover_color=CARD2, font=ctk.CTkFont(size=11),
            command=self._deselect_all,
        ).pack(side="left")

        # Scan status label
        self.scan_status_lbl = ctk.CTkLabel(
            tab, textvariable=self._scan_status_var,
            font=ctk.CTkFont(size=11), text_color=YELLOW,
        )
        self.scan_status_lbl.pack(anchor="w", padx=4, pady=(0, 3))

        # Scrollable app list
        self.app_list_frame = ctk.CTkScrollableFrame(
            tab, fg_color=BG, corner_radius=10,
        )
        self.app_list_frame.pack(fill="both", expand=True, padx=4, pady=(0, 8))

        # Save row
        save_row = ctk.CTkFrame(tab, fg_color="transparent")
        save_row.pack(fill="x", padx=4, pady=(0, 10))
        self.apps_status_lbl = ctk.CTkLabel(
            save_row, text="", font=ctk.CTkFont(size=11), text_color=SUBTEXT,
        )
        self.apps_status_lbl.pack(side="left")
        ctk.CTkButton(
            save_row, text="Save Changes",
            font=ctk.CTkFont(size=13, weight="bold"),
            fg_color=ACCENT, hover_color="#2563eb",
            height=38, width=140, command=self._save_blocked_apps,
        ).pack(side="right")

    def _scan_apps_thread(self, cfg):
        apps = scan_installed_apps()
        self.after(0, self._on_scan_complete, apps, cfg)

    def _on_scan_complete(self, apps, cfg):
        self._all_apps = apps
        blocked_set = set(cfg.get("blocked_apps", []))
        self._app_rows = [
            (exe, name, tk.BooleanVar(value=(exe in blocked_set)))
            for exe, name in apps
        ]
        self._scan_status_var.set(f"{len(apps)} apps found")
        self.scan_status_lbl.configure(text_color=SUBTEXT)
        self._render_app_list(self._app_rows)
        self._update_blocked_count()

    def _render_app_list(self, rows):
        for w in self.app_list_frame.winfo_children():
            w.destroy()

        if not rows:
            ctk.CTkLabel(
                self.app_list_frame,
                text="No apps match your search.",
                font=ctk.CTkFont(size=12), text_color=SUBTEXT,
            ).pack(pady=20)
            return

        for exe, display_name, var in rows:
            row = ctk.CTkFrame(self.app_list_frame, fg_color="transparent")
            row.pack(fill="x", pady=1)
            ctk.CTkCheckBox(
                row, text=display_name, variable=var,
                font=ctk.CTkFont(size=13), text_color=TEXT,
                fg_color=ACCENT, hover_color="#2563eb", checkmark_color="white",
                command=self._update_blocked_count,
            ).pack(side="left", padx=10, pady=5)
            ctk.CTkLabel(
                row, text=exe,
                font=ctk.CTkFont(size=10), text_color=BORDER,
            ).pack(side="right", padx=10)

    def _filter_apps(self):
        if not hasattr(self, "_app_rows"):
            return
        query = self.search_var.get().lower().strip()
        filtered = self._app_rows if not query else [
            (exe, name, var) for exe, name, var in self._app_rows
            if query in name.lower() or query in exe.lower()
        ]
        self._render_app_list(filtered)

    def _update_blocked_count(self):
        if not hasattr(self, "_app_rows"):
            return
        total    = len(self._app_rows)
        selected = sum(1 for _, _, var in self._app_rows if var.get())
        self.blocked_count_lbl.configure(
            text=f"{selected} blocked / {total} total",
            text_color=RED if selected > 0 else SUBTEXT,
        )

    def _select_all_visible(self):
        query = self.search_var.get().lower().strip()
        for exe, name, var in self._app_rows:
            if not query or query in name.lower() or query in exe.lower():
                var.set(True)
        self._update_blocked_count()

    def _deselect_all(self):
        for _, _, var in self._app_rows:
            var.set(False)
        self._update_blocked_count()

    def _save_blocked_apps(self):
        new_blocked = set(exe for exe, _, var in self._app_rows if var.get())
        removed     = self._initially_blocked - new_blocked

        if removed:
            # Removing apps from the blocked list requires a password
            PasswordDialog(
                self,
                prompt="Enter password to remove apps from the blocked list:",
                on_success=lambda: self._do_save_blocked_apps(new_blocked),
                on_fail=lambda: self.apps_status_lbl.configure(
                    text="Cancelled — no changes made.", text_color=YELLOW,
                ),
            )
        else:
            self._do_save_blocked_apps(new_blocked)

    def _do_save_blocked_apps(self, new_blocked: set):
        cfg = load_config()
        cfg["blocked_apps"] = sorted(new_blocked)
        save_config(cfg)
        self._initially_blocked = new_blocked.copy()
        count = len(new_blocked)
        self.apps_status_lbl.configure(
            text=f"✓  Saved — {count} app{'s' if count != 1 else ''} blocked.",
            text_color=GREEN,
        )
        log(f"Blocked apps updated: {sorted(new_blocked)}")

    # ── Admin Tab ───────────────────────────────────────────────────────────────

    def _build_admin_tab(self, tab, cfg):
        content = ctk.CTkScrollableFrame(tab, fg_color="transparent")
        content.pack(fill="both", expand=True, padx=4, pady=4)

        # GitHub credentials
        self._section(content, "GitHub Credentials")
        ctk.CTkLabel(
            content, text="GitHub Username",
            font=ctk.CTkFont(size=12), text_color=SUBTEXT,
        ).pack(anchor="w")
        self.gh_user = ctk.CTkEntry(
            content, height=38, fg_color=BG, border_color=BORDER,
            text_color=TEXT, font=ctk.CTkFont(size=13),
        )
        self.gh_user.insert(0, cfg.get("github_username", ""))
        self.gh_user.pack(fill="x", pady=(2, 10))

        ctk.CTkLabel(
            content,
            text="GitHub Personal Access Token  (optional — enables private repo detection)",
            font=ctk.CTkFont(size=12), text_color=SUBTEXT,
        ).pack(anchor="w")
        self.gh_token = ctk.CTkEntry(
            content, height=38, fg_color=BG, border_color=BORDER,
            text_color=TEXT, show="●", font=ctk.CTkFont(size=13),
        )
        self.gh_token.insert(0, decrypt_token(cfg.get("github_token", "")))
        self.gh_token.pack(fill="x", pady=(2, 12))

        # Admin password change
        self._section(content, "Admin Password")
        ctk.CTkLabel(
            content, text="Change Password  (leave blank to keep current)",
            font=ctk.CTkFont(size=12), text_color=SUBTEXT,
        ).pack(anchor="w")
        self.new_pw = ctk.CTkEntry(
            content, height=38, fg_color=BG, border_color=BORDER,
            text_color=TEXT, show="●", font=ctk.CTkFont(size=13),
            placeholder_text="New password…",
        )
        self.new_pw.pack(fill="x", pady=(2, 4))
        self.confirm_pw = ctk.CTkEntry(
            content, height=38, fg_color=BG, border_color=BORDER,
            text_color=TEXT, show="●", font=ctk.CTkFont(size=13),
            placeholder_text="Confirm password…",
        )
        self.confirm_pw.pack(fill="x", pady=(2, 12))

        # Save button + status
        save_row = ctk.CTkFrame(content, fg_color="transparent")
        save_row.pack(fill="x", pady=(4, 0))
        self.admin_status_lbl = ctk.CTkLabel(
            save_row, text="", font=ctk.CTkFont(size=12), text_color=SUBTEXT,
        )
        self.admin_status_lbl.pack(side="left")
        ctk.CTkButton(
            save_row, text="Save Admin Settings",
            font=ctk.CTkFont(size=13, weight="bold"),
            fg_color=ACCENT, hover_color="#2563eb",
            height=40, width=180, command=self._save_admin,
        ).pack(side="right")

    def _section(self, parent, title: str):
        ctk.CTkFrame(parent, fg_color=BORDER, height=1).pack(fill="x", pady=(4, 10))
        ctk.CTkLabel(
            parent, text=title,
            font=ctk.CTkFont(size=13, weight="bold"), text_color=TEXT,
        ).pack(anchor="w", pady=(0, 6))

    def _save_admin(self):
        cfg = load_config()
        cfg["github_username"] = self.gh_user.get().strip()
        cfg["github_token"]    = encrypt_token(self.gh_token.get().strip())

        new_pw  = self.new_pw.get()
        conf_pw = self.confirm_pw.get()
        if new_pw or conf_pw:
            if new_pw != conf_pw:
                self.admin_status_lbl.configure(
                    text="✗  Passwords do not match.", text_color=RED,
                )
                return
            if len(new_pw) < 6:
                self.admin_status_lbl.configure(
                    text="✗  Password must be at least 6 characters.", text_color=RED,
                )
                return
            cfg["password_hash"] = hash_password(new_pw)
            self.new_pw.delete(0, "end")
            self.confirm_pw.delete(0, "end")

        save_config(cfg)
        self.admin_status_lbl.configure(text="✓  Admin settings saved.", text_color=GREEN)
        log("Admin settings saved via GUI.")


# ── Entry point ─────────────────────────────────────────────────────────────────

def main():
    firstrun = "/firstrun" in sys.argv
    app = ScreenLimiterApp(firstrun=firstrun)
    app.mainloop()


if __name__ == "__main__":
    main()
