"""
assignments_ui.py — Standalone window for managing the assignment list.
Launched from the system tray icon.
"""

import sys
import os
import uuid
import tkinter as tk
import customtkinter as ctk

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from shared import load_assignments, save_assignments

ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")

ACCENT  = "#3b82f6"
RED     = "#ef4444"
GREEN   = "#22c55e"
BG      = "#0f172a"
CARD    = "#1e293b"
CARD2   = "#273449"
TEXT    = "#f1f5f9"
SUBTEXT = "#94a3b8"
BORDER  = "#334155"


class AssignmentsWindow(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("Screen Limiter — Assignments")
        self.geometry("560x620")
        self.resizable(False, False)
        self.configure(fg_color=BG)
        self.attributes("-topmost", True)
        self.lift()

        self._build_ui()
        self._refresh()

    def _build_ui(self):
        # ── Header ─────────────────────────────────────────────────────────────
        header = ctk.CTkFrame(self, fg_color=CARD, corner_radius=0, height=72)
        header.pack(fill="x")
        header.pack_propagate(False)
        ctk.CTkLabel(
            header,
            text="📋  Assignment Manager",
            font=ctk.CTkFont(size=18, weight="bold"),
            text_color=TEXT
        ).pack(side="left", padx=20, pady=16)
        ctk.CTkLabel(
            header,
            text="All items must be checked to unlock blocked apps.",
            font=ctk.CTkFont(size=11),
            text_color=SUBTEXT
        ).pack(side="left", padx=(0, 20), pady=16)

        # ── Add new assignment ─────────────────────────────────────────────────
        add_row = ctk.CTkFrame(self, fg_color="transparent")
        add_row.pack(fill="x", padx=20, pady=(16, 8))

        self.new_entry = ctk.CTkEntry(
            add_row,
            placeholder_text="e.g.  Chapter 5 reading, Problem set 3…",
            font=ctk.CTkFont(size=13),
            height=40,
            fg_color=CARD,
            border_color=BORDER,
            text_color=TEXT
        )
        self.new_entry.pack(side="left", fill="x", expand=True, padx=(0, 8))
        self.new_entry.bind("<Return>", lambda _: self._add_assignment())

        ctk.CTkButton(
            add_row,
            text="+ Add",
            font=ctk.CTkFont(size=13, weight="bold"),
            fg_color=ACCENT,
            hover_color="#2563eb",
            width=80,
            height=40,
            command=self._add_assignment
        ).pack(side="left")

        # ── Divider + list header ──────────────────────────────────────────────
        ctk.CTkFrame(self, fg_color=BORDER, height=1).pack(fill="x", padx=20)

        list_header = ctk.CTkFrame(self, fg_color="transparent")
        list_header.pack(fill="x", padx=20, pady=(8, 4))
        ctk.CTkLabel(
            list_header,
            text="Today's Assignments",
            font=ctk.CTkFont(size=13, weight="bold"),
            text_color=TEXT
        ).pack(side="left")
        self.count_label = ctk.CTkLabel(
            list_header,
            text="",
            font=ctk.CTkFont(size=11),
            text_color=SUBTEXT
        )
        self.count_label.pack(side="right")

        # ── Scrollable list ────────────────────────────────────────────────────
        self.list_frame = ctk.CTkScrollableFrame(
            self,
            fg_color=CARD,
            corner_radius=10,
            height=340
        )
        self.list_frame.pack(fill="both", expand=True, padx=20, pady=(0, 8))

        # ── Bottom buttons ─────────────────────────────────────────────────────
        btn_row = ctk.CTkFrame(self, fg_color="transparent")
        btn_row.pack(fill="x", padx=20, pady=(0, 16))

        ctk.CTkButton(
            btn_row,
            text="✓  Mark All Done",
            font=ctk.CTkFont(size=12),
            fg_color=GREEN,
            hover_color="#16a34a",
            height=36,
            command=self._mark_all_done
        ).pack(side="left", padx=(0, 8))

        ctk.CTkButton(
            btn_row,
            text="↺  Reset All",
            font=ctk.CTkFont(size=12),
            fg_color="transparent",
            hover_color=CARD2,
            border_color=BORDER,
            border_width=1,
            text_color=SUBTEXT,
            height=36,
            command=self._reset_all
        ).pack(side="left", padx=(0, 8))

        ctk.CTkButton(
            btn_row,
            text="🗑  Clear Completed",
            font=ctk.CTkFont(size=12),
            fg_color="transparent",
            hover_color=CARD2,
            border_color=BORDER,
            border_width=1,
            text_color=SUBTEXT,
            height=36,
            command=self._clear_completed
        ).pack(side="left")

    # ── Data methods ───────────────────────────────────────────────────────────

    def _refresh(self):
        for w in self.list_frame.winfo_children():
            w.destroy()

        assignments = load_assignments()
        done_count  = sum(1 for a in assignments if a.get("done"))
        total       = len(assignments)
        self.count_label.configure(text=f"{done_count}/{total} done")

        if not assignments:
            ctk.CTkLabel(
                self.list_frame,
                text="No assignments yet. Add one above!",
                font=ctk.CTkFont(size=13),
                text_color=SUBTEXT
            ).pack(pady=32)
            return

        for a in assignments:
            self._render_row(a)

    def _render_row(self, assignment: dict):
        row = ctk.CTkFrame(self.list_frame, fg_color=CARD2, corner_radius=8)
        row.pack(fill="x", pady=3, padx=4)

        var = tk.BooleanVar(value=assignment.get("done", False))

        cb = ctk.CTkCheckBox(
            row,
            text=assignment["text"],
            variable=var,
            font=ctk.CTkFont(size=13),
            text_color=SUBTEXT if assignment.get("done") else TEXT,
            fg_color=ACCENT,
            hover_color="#2563eb",
            checkmark_color="white",
            command=lambda a=assignment, v=var: self._toggle(a, v)
        )
        cb.pack(side="left", padx=12, pady=10)

        ctk.CTkButton(
            row,
            text="✕",
            width=28,
            height=28,
            fg_color="transparent",
            hover_color=RED,
            text_color=SUBTEXT,
            font=ctk.CTkFont(size=11, weight="bold"),
            command=lambda a=assignment: self._delete(a)
        ).pack(side="right", padx=8)

    def _add_assignment(self):
        text = self.new_entry.get().strip()
        if not text:
            return
        assignments = load_assignments()
        assignments.append({"id": str(uuid.uuid4()), "text": text, "done": False})
        save_assignments(assignments)
        self.new_entry.delete(0, "end")
        self._refresh()

    def _toggle(self, assignment: dict, var: tk.BooleanVar):
        assignments = load_assignments()
        for a in assignments:
            if a["id"] == assignment["id"]:
                a["done"] = var.get()
        save_assignments(assignments)
        self._refresh()

    def _delete(self, assignment: dict):
        assignments = [a for a in load_assignments() if a["id"] != assignment["id"]]
        save_assignments(assignments)
        self._refresh()

    def _mark_all_done(self):
        assignments = load_assignments()
        for a in assignments:
            a["done"] = True
        save_assignments(assignments)
        self._refresh()

    def _reset_all(self):
        assignments = load_assignments()
        for a in assignments:
            a["done"] = False
        save_assignments(assignments)
        self._refresh()

    def _clear_completed(self):
        assignments = [a for a in load_assignments() if not a.get("done")]
        save_assignments(assignments)
        self._refresh()


def main():
    app = AssignmentsWindow()
    app.mainloop()


if __name__ == "__main__":
    main()
