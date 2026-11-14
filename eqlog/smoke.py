"""Packaged runtime check; writes results without a console or real player logs."""
from dataclasses import asdict
import json
from pathlib import Path
import tempfile
import tkinter as tk

from .core import clean


def run(destination):
    result = {"ok": False}
    try:
        root = tk.Tk()
        root.withdraw()
        root.update()
        result["tk_version"] = root.tk.call("info", "patchlevel")
        root.destroy()
        with tempfile.TemporaryDirectory(prefix="eqlog-smoke-") as directory:
            path = Path(directory) / "eqlog_Smoke_test.txt"
            stamp = b"[Fri Nov 13 12:00:00 2026] "
            kept = stamp + b"You have entered Freeport.\r\n"
            original = kept + stamp + b"Bob says, 'old chat'\r\n"
            addition = stamp + b"Bob says, 'new chat'\r\n"
            path.write_bytes(original)
            first = clean(path, offline=True)
            assert path.read_bytes() == kept
            assert first.backup.read_bytes() == original
            with path.open("ab") as file:
                file.write(addition)
            second = clean(path, offline=True)
            assert second.backup == first.backup
            assert second.backup.read_bytes() == original + addition
            assert path.read_bytes() == kept
            clean(path, offline=True)
            assert first.backup.read_bytes() == original + addition
            result.update(ok=True, backup_verified=True, cumulative_append_verified=True,
                          repeat_without_duplicate=True, report=asdict(second))
    except Exception as exc:
        result["error"] = f"{type(exc).__name__}: {exc}"
    Path(destination).write_text(json.dumps(result, indent=2, default=str) + "\n", encoding="utf-8")
    return 0 if result["ok"] else 1
