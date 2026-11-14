"""Small desktop interface; all file processing runs off the UI thread."""
from concurrent.futures import ThreadPoolExecutor
import os
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from .core import clean, preview

BG = "#0f1115"
PANEL = "#171a21"
GOLD = "#d9b25f"
TEXT = "#e8e9ed"
MUTED = "#9ba2b2"
FONT = "Segoe UI" if os.name == "nt" else "Helvetica"


def size(value):
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if value < 1024 or unit == "TB":
            return f"{value:,.1f} {unit}"
        value /= 1024


class App:
    def __init__(self, root):
        self.root = root
        self.executor = ThreadPoolExecutor(max_workers=1)
        self.report = None
        self.busy = False
        self.acknowledged = False
        root.title("EQLog · Legends Log Cleaner")
        root.geometry("960x800")
        root.minsize(860, 760)
        root.configure(bg=BG)
        root.option_add("*Font", (FONT, 10))
        style = ttk.Style(root)
        style.theme_use("clam")
        style.configure("TButton", background=PANEL, foreground=TEXT, padding=(18, 11), borderwidth=0)
        style.map("TButton", background=[("active", "#252b36")], foreground=[("disabled", "#656d7a")])
        style.configure("Gold.TButton", background=GOLD, foreground=BG, font=(FONT, 10, "bold"))
        style.map("Gold.TButton", background=[("disabled", "#34332e"), ("active", "#ecc77c")],
                  foreground=[("disabled", "#858078")])
        style.configure("TCheckbutton", background=BG, foreground=MUTED, padding=0)
        style.map("TCheckbutton", background=[("active", BG)], foreground=[("active", TEXT)])
        style.configure("TProgressbar", background=GOLD, troughcolor=PANEL, borderwidth=0)
        outer = tk.Frame(root, bg=BG, padx=32, pady=24)
        outer.pack(fill="both", expand=True)
        self.label(outer, "EQ LOG", GOLD, 12, True).pack(anchor="w")
        self.label(outer, "A lighter log. The same adventures.", TEXT, 24, True).pack(anchor="w", pady=(8, 7))
        self.label(outer, "Backup-first cleanup for EverQuest Legends", MUTED, 11).pack(anchor="w")

        card = tk.Frame(outer, bg=PANEL, padx=20, pady=18)
        card.pack(fill="x", pady=(24, 16))
        self.label(card, "01   SELECT YOUR LOG", GOLD, 10, True).pack(anchor="w")
        row = tk.Frame(card, bg=PANEL)
        row.pack(fill="x", pady=(14, 0))
        self.path = tk.StringVar()
        self.entry = tk.Entry(row, textvariable=self.path, bg=BG, fg=TEXT, insertbackground=GOLD,
                              disabledbackground=BG, disabledforeground=MUTED,
                              relief="flat", font=(FONT, 10))
        self.entry.pack(side="left", fill="x", expand=True, ipady=12, padx=(0, 12))
        self.browse_button = ttk.Button(row, text="Browse...", command=self.browse)
        self.browse_button.pack(side="right")
        self.path.trace_add("write", self.invalidate)

        stats = tk.Frame(outer, bg=BG)
        stats.pack(fill="x", pady=(0, 16))
        self.values = []
        for index, title in enumerate(("CURRENT SIZE", "AFTER CLEANUP", "SPACE SAVED")):
            stats.columnconfigure(index, weight=1, uniform="stats")
            box = tk.Frame(stats, bg=PANEL, padx=18, pady=16)
            box.grid(row=0, column=index, sticky="nsew", padx=(0 if index == 0 else 8, 0))
            self.label(box, title, MUTED, 9, True).pack(anchor="w")
            value = self.label(box, "-", GOLD if index == 2 else TEXT, 23, True)
            value.pack(anchor="w", pady=(8, 0))
            self.values.append(value)

        details = tk.Frame(outer, bg=PANEL, padx=20, pady=16)
        details.pack(fill="x")
        self.label(details, "02   PREVIEW & PROTECT", GOLD, 10, True).pack(anchor="w")
        self.detail = tk.StringVar(value="Analyze a log to see how much ordinary chat can be removed.")
        tk.Label(details, textvariable=self.detail, bg=PANEL, fg=TEXT, justify="left",
                 wraplength=730, anchor="w").pack(fill="x", pady=(12, 8))
        self.label(details, "Keeps combat, loot, spells, pets, progression and unknown messages.", MUTED, 10).pack(anchor="w")
        self.label(details, "Your original backup keeps its history and adds new log data each cleanup.", MUTED, 10).pack(anchor="w", pady=(4, 0))

        self.offline = tk.BooleanVar(value=False)
        self.check = ttk.Checkbutton(outer, text="I have closed EverQuest and Companion before cleaning.",
                                    variable=self.offline, command=self.update_buttons)
        self.check.pack(anchor="w", pady=(18, 12))
        actions = tk.Frame(outer, bg=BG)
        actions.pack(fill="x")
        self.analyze = ttk.Button(actions, text="Analyze log", command=self.run_preview)
        self.analyze.pack(side="left")
        self.apply = ttk.Button(actions, text="Back up & clean", style="Gold.TButton", command=self.run_clean)
        self.apply.pack(side="right")
        self.progress = ttk.Progressbar(outer, mode="indeterminate")
        self.progress.pack(fill="x", pady=(16, 9))
        self.status = tk.StringVar(value="Ready. Analyze does not change your log.")
        tk.Label(outer, textvariable=self.status, bg=BG, fg=MUTED, justify="left", anchor="w",
                 wraplength=790).pack(fill="x")
        self.update_buttons()
        root.protocol("WM_DELETE_WINDOW", self.close)
        root.after_idle(self.show_startup_warning)

    def show_startup_warning(self):
        if not self.root.winfo_viewable():
            self.root.after(50, self.show_startup_warning)
            return
        dialog = tk.Toplevel(self.root)
        self.warning = dialog
        dialog.title("Close EverQuest and Companion")
        dialog.configure(bg=PANEL, padx=28, pady=24)
        dialog.resizable(False, False)
        dialog.transient(self.root)
        self.label(dialog, "Close both apps before continuing", GOLD, 16, True).pack(anchor="w")
        tk.Label(dialog, text="EverQuest and EverQuest Companion must be closed before you use "
                 "EQLog. Keep both apps closed until cleanup finishes.\n\n"
                 "Click OK to confirm you have closed both apps.",
                 bg=PANEL, fg=TEXT, justify="left", wraplength=470,
                 font=(FONT, 11)).pack(anchor="w", pady=(16, 22))
        self.warning_ok = ttk.Button(dialog, text="OK", style="Gold.TButton",
                                     command=self.confirm_startup)
        self.warning_ok.pack(anchor="e")
        dialog.protocol("WM_DELETE_WINDOW", self.close)
        dialog.update_idletasks()
        x = self.root.winfo_rootx() + (self.root.winfo_width() - dialog.winfo_reqwidth()) // 2
        y = self.root.winfo_rooty() + (self.root.winfo_height() - dialog.winfo_reqheight()) // 2
        dialog.geometry(f"+{max(0, x)}+{max(0, y)}")
        dialog.wait_visibility()
        dialog.grab_set()
        self.warning_ok.focus_set()

    def confirm_startup(self):
        self.acknowledged = True
        self.offline.set(True)
        self.warning.grab_release()
        self.warning.destroy()
        self.update_buttons()

    @staticmethod
    def label(parent, text, color, size_, bold=False):
        return tk.Label(parent, text=text, bg=parent["bg"], fg=color,
                        font=(FONT, size_, "bold" if bold else "normal"))

    def browse(self):
        path = filedialog.askopenfilename(title="Choose an EverQuest Legends log",
                                          filetypes=[("EverQuest logs", "eqlog_*.txt"), ("All files", "*")])
        if path:
            self.path.set(path)

    def invalidate(self, *_):
        self.report = None
        for label in self.values:
            label.configure(text="-")
        self.update_buttons()

    def update_buttons(self):
        enabled = not self.busy and self.acknowledged
        self.analyze.configure(state="normal" if enabled and self.path.get().strip() else "disabled")
        self.apply.configure(state="normal" if enabled and self.report
                             and self.offline.get() else "disabled")
        self.browse_button.configure(state="normal" if enabled else "disabled")
        self.entry.configure(state="normal" if enabled else "disabled")
        self.check.configure(state="normal" if enabled else "disabled")

    def work(self, function, done):
        self.busy = True
        self.update_buttons()
        self.progress.start(12)
        future = self.executor.submit(function)

        def poll():
            if not future.done():
                self.root.after(80, poll)
                return
            self.busy = False
            self.progress.stop()
            try:
                done(future.result())
            except Exception as exc:
                self.report = None
                self.status.set("Cleanup stopped. See details for the outcome.")
                messagebox.showerror("Could not complete cleanup", str(exc))
            self.update_buttons()
        self.root.after(80, poll)

    def run_preview(self):
        if not self.acknowledged or self.busy:
            return
        path = self.path.get().strip()
        self.status.set("Analyzing your log...")
        self.work(lambda: preview(path), self.show_preview)

    def show_preview(self, report):
        self.report = report
        for label, text in zip(self.values, (size(report.original_bytes), size(report.cleaned_bytes),
                                             f"{report.reduction:.1f}%")):
            label.configure(text=text)
        self.detail.set(f"{report.removed_lines:,} of {report.total_lines:,} lines can be removed · "
                        f"{size(report.saved_bytes)} saved\n" +
                        ("  |  ".join(f"{k}: {v:,}" for k, v in report.reasons.items())
                         or "Nothing to remove. You can still update your original backup."))
        self.status.set("Preview complete. Your log has not been changed.")

    def run_clean(self):
        report = self.report
        if not self.acknowledged or self.busy or not report or not self.offline.get():
            return
        self.status.set("Creating and verifying backup, then cleaning...")
        self.work(lambda: clean(report.path, offline=True, expected_sha256=report.sha256), self.show_clean)

    def show_clean(self, report):
        self.report = None
        self.detail.set(f"Cleaned successfully · {size(report.saved_bytes)} saved\n"
                        "Original log filename preserved. Backup verified with SHA-256.")
        self.status.set(f"Backup: {report.backup}")

    def close(self):
        if self.busy:
            messagebox.showinfo("Cleanup in progress", "Please wait for the current operation to finish.")
            return
        self.executor.shutdown(wait=False)
        self.root.destroy()


def main():
    root = tk.Tk()
    App(root)
    root.mainloop()
