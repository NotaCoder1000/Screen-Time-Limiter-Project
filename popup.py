"""
popup.py — The interception popup shown when a blocked app is launched.

Flow:
  1. Show assignments checklist — user must tick every item.
  2. On confirm, check GitHub for a commit today.
  3. If both pass  → write an approval token and exit 0  (service resumes the process)
  4. If either fails → exit 1  (service kills the process)

Usage (called by the service):
    python popup.py <pid> <app_name>
"""

import sys
import os
import datetime
import threading
import tkinter as tk
from tkinter import font as tkfont
import customtkinter as ctk

# Add project dir to path so we can import siblings
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from shared import load_assignments, save_assignments, all_assignments_done, load_config, log
from github_check import has_commit_today

# ── Appearance ─────────────────────────────────────────────────────────────────
ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")

ACCENT   = "#3b82f6"
RED      = "#ef4444"
GREEN    = "#22c55e"
YELLOW   = "#f59e0b"
BG       = "#0f172a"
CARD     = "#1e293b"
TEXT     = "#f1f5f9"
SUBTEXT  = "#94a3b8"


class InterceptPopup(ctk.CTk):
    def __init__(self, pid: int, app_name: str):
        super().__init__()
        self.pid       = pid
        self.app_name  = app_name
        self.result    = False   # True = allow, False = deny
        self.checking  = False

        self.title("Screen Limiter — Access Check")
        self.geometry("520x640")
        self.resizable(False, False)
        self.configure(fg_color=BG)

        # Force window to front and keep on top
        self.attributes("-topmost", True)
        self.lift()
        self.focus_force()

        # Prevent closing with X button (forces a decision)
        self.protocol("WM_DELETE_WINDOW", self._on_force_close)

        self._build_ui()
        self._load_assignments()

    # ── UI construction ────────────────────────────────────────────────────────

    def _build_ui(self):
        # Header
        header = ctk.CTkFrame(self, fg_color=CARD, corner_radius=0, height=80)
        header.pack(fill="x")
        header.pack_propagate(False)

        ctk.CTkLabel(
            header,
            text=f"⚠  You're trying to open  {self.app_name}",
            font=ctk.CTkFont(size=15, weight="bold"),
            text_color=YELLOW
        ).pack(pady=(18, 2))
        ctk.CTkLabel(
            header,
            text="Complete the checks below to get access.",
            font=ctk.CTkFont(size=12),
            text_color=SUBTEXT
        ).pack()

        # ── Step 1: Assignments ────────────────────────────────────────────────
        s1_label = ctk.CTkFrame(self, fg_color="transparent")
        s1_label.pack(fill="x", padx=24, pady=(20, 4))
        ctk.CTkLabel(
            s1_label,
            text="Step 1 — Complete your assignments",
            font=ctk.CTkFont(size=13, weight="bold"),
            text_color=TEXT
        ).pack(anchor="w")

        # Scrollable assignments area
        self.assign_frame = ctk.CTkScrollableFrame(
            self, fg_color=CARD, corner_radius=10, height=220
        )
        self.assign_frame.pack(fill="x", padx=24, pady=(0, 8))

        self.checkboxes   = []   # list of (var, assignment_dict, checkbox_widget)
        self.no_tasks_lbl = None

        # ── Step 2: GitHub ─────────────────────────────────────────────────────
        s2_frame = ctk.CTkFrame(self, fg_color="transparent")
        s2_frame.pack(fill="x", padx=24, pady=(4, 0))
        ctk.CTkLabel(
            s2_frame,
            text="Step 2 — GitHub commit check",
            font=ctk.CTkFont(size=13, weight="bold"),
            text_color=TEXT
        ).pack(anchor="w")

        self.github_status = ctk.CTkLabel(
            self,
            text="○  Will check after assignments confirmed",
            font=ctk.CTkFont(size=12),
            text_color=SUBTEXT
        )
        self.github_status.pack(padx=24, pady=(4, 16), anchor="w")

        # ── Confirm button ─────────────────────────────────────────────────────
        self.confirm_btn = ctk.CTkButton(
            self,
            text="Confirm Assignments & Check GitHub",
            font=ctk.CTkFont(size=13, weight="bold"),
            fg_color=ACCENT,
            hover_color="#2563eb",
            height=44,
            command=self._on_confirm
        )
        self.confirm_btn.pack(fill="x", padx=24, pady=(0, 8))

        # Deny button
        ctk.CTkButton(
            self,
            text="Cancel — don't open this app",
            font=ctk.CTkFont(size=12),
            fg_color="transparent",
            hover_color="#1e293b",
            border_color="#334155",
            border_width=1,
            text_color=SUBTEXT,
            height=36,
            command=self._deny
        ).pack(fill="x", padx=24, pady=(0, 16))

        # Status bar
        self.status_bar = ctk.CTkLabel(
            self,
            text="",
            font=ctk.CTkFont(size=11),
            text_color=SUBTEXT
        )
        self.status_bar.pack(pady=(0, 8))

    # ── Assignment loading ─────────────────────────────────────────────────────

    def _load_assignments(self):
        # Clear existing widgets
        for widget in self.assign_frame.winfo_children():
            widget.destroy()
        self.checkboxes = []

        assignments = load_assignments()

        if not assignments:
            self.no_tasks_lbl = ctk.CTkLabel(
                self.assign_frame,
                text="No assignments added yet.\nUse the tray icon → 'Manage Assignments' to add tasks.",
                font=ctk.CTkFont(size=12),
                text_color=SUBTEXT,
                justify="center"
            )
            self.no_tasks_lbl.pack(pady=24)
            return

        for a in assignments:
            var = tk.BooleanVar(value=a.get("done", False))
            row = ctk.CTkFrame(self.assign_frame, fg_color="transparent")
            row.pack(fill="x", pady=3)
            cb = ctk.CTkCheckBox(
                row,
                text=a["text"],
                variable=var,
                font=ctk.CTkFont(size=13),
                text_color=TEXT,
                fg_color=ACCENT,
                hover_color="#2563eb",
                checkmark_color="white"
            )
            cb.pack(anchor="w", padx=8)
            self.checkboxes.append((var, a, cb))

    # ── Actions ────────────────────────────────────────────────────────────────

    def _on_confirm(self):
        if self.checking:
            return
        self.checking = True
        self.confirm_btn.configure(state="disabled", text="Checking…")

        # Persist checkbox states
        assignments = load_assignments()
        checked_ids = {a["id"] for (var, a, _) in self.checkboxes if var.get()}
        for a in assignments:
            a["done"] = (a["id"] in checked_ids)
        save_assignments(assignments)

        # Check all done
        if not all(var.get() for (var, _, __) in self.checkboxes) and self.checkboxes:
            self._set_status("✗  Please tick all assignments before proceeding.", RED)
            self.confirm_btn.configure(state="normal", text="Confirm Assignments & Check GitHub")
            self.checking = False
            return

        # Run GitHub check in background thread so UI doesn't freeze
        self._set_status("Checking GitHub…", YELLOW)
        self.github_status.configure(text="⏳  Contacting GitHub…", text_color=YELLOW)
        threading.Thread(target=self._github_check_thread, daemon=True).start()

    def _github_check_thread(self):
        is_weekend = datetime.date.today().weekday() >= 5
        if is_weekend:
            ok, reason = True, "Weekend — GitHub check skipped ✓"
        else:
            ok, reason = has_commit_today()

        # Marshal back to main thread
        self.after(0, self._on_github_result, ok, reason)

    def _on_github_result(self, ok: bool, reason: str):
        if ok:
            self.github_status.configure(text=f"✓  {reason}", text_color=GREEN)
            self._allow()
        else:
            self.github_status.configure(text=f"✗  {reason}", text_color=RED)
            self._set_status("Access denied — push a commit first, then try again.", RED)
            self.confirm_btn.configure(
                state="normal",
                text="Re-check GitHub"
            )
            self.checking = False

    def _allow(self):
        log(f"ALLOW: {self.app_name} (pid {self.pid})")
        self.result = True
        self.after(600, self.destroy)

    def _deny(self):
        log(f"DENY (user cancelled): {self.app_name} (pid {self.pid})")
        self.result = False
        self.destroy()

    def _on_force_close(self):
        # Closing the window = deny
        self._deny()

    def _set_status(self, msg: str, color: str = SUBTEXT):
        self.status_bar.configure(text=msg, text_color=color)


# ── Entry point ────────────────────────────────────────────────────────────────

def main():
    if len(sys.argv) < 3:
        print("Usage: popup.py <pid> <app_name>")
        sys.exit(1)

    pid      = int(sys.argv[1])
    app_name = sys.argv[2]

    app = InterceptPopup(pid, app_name)
    app.mainloop()

    # Exit code tells the service what to do
    sys.exit(0 if app.result else 1)


if __name__ == "__main__":
    main()
