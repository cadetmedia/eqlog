import os
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import patch


@unittest.skipUnless(os.environ.get("DISPLAY") or os.name == "nt", "A desktop display is required")
class DesktopTests(unittest.TestCase):
    def test_preview_then_backup_and_clean_through_window(self):
        import tkinter as tk
        from eqlog.app import App

        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "eqlog_Bob_freeport.txt"
            kept = b"[Fri Nov 13 12:00:00 2026] You have entered Freeport.\r\n"
            chat = b"[Fri Nov 13 12:00:00 2026] Bob says, 'hello'\r\n"
            original = kept + chat * 100
            path.write_bytes(original)
            root = tk.Tk()
            app = App(root)
            errors = patch("eqlog.app.messagebox.showerror")
            error_dialog = errors.start()
            self.addCleanup(errors.stop)
            self.addCleanup(root.destroy)
            self.addCleanup(app.executor.shutdown)

            def finish():
                deadline = time.monotonic() + 10
                while app.busy and time.monotonic() < deadline:
                    root.update()
                    time.sleep(0.01)
                self.assertFalse(app.busy, "The background operation did not finish")
                root.update()
                if error_dialog.called:
                    self.fail(f"Desktop operation failed: {error_dialog.call_args}")

            deadline = time.monotonic() + 5
            while not hasattr(app, "warning_ok") and time.monotonic() < deadline:
                root.update()
                time.sleep(0.01)
            self.assertTrue(app.warning.winfo_exists())
            app.path.set(str(path))
            self.assertEqual(str(app.analyze["state"]), "disabled")
            self.assertEqual(str(app.apply["state"]), "disabled")
            app.run_preview()
            self.assertFalse(app.busy)
            app.warning_ok.invoke()
            self.assertTrue(app.acknowledged)
            self.assertTrue(app.offline.get())
            app.offline.set(False)
            self.assertEqual(str(app.apply["state"]), "disabled")
            app.path.set(str(path))
            app.analyze.invoke()
            finish()
            self.assertEqual(app.report.removed_lines, 100)
            self.assertEqual(path.read_bytes(), original)
            self.assertEqual(str(app.apply["state"]), "disabled")
            app.offline.set(True)
            app.update_buttons()
            self.assertEqual(str(app.apply["state"]), "normal")
            app.apply.invoke()
            finish()
            self.assertEqual(path.read_bytes(), kept)
            backup = next(path.parent.glob("*.original-backup.txt.bak"))
            self.assertEqual(backup.read_bytes(), original)
            self.assertIn("Backup:", app.status.get())
            self.assertEqual(str(app.apply["state"]), "disabled")

            # A combat-only addition must still be archivable even if there is
            # nothing to remove from the live file.
            new = b"[Fri Nov 13 12:01:00 2026] You gain experience!\r\n"
            with path.open("ab") as file:
                file.write(new)
            app.analyze.invoke()
            finish()
            self.assertEqual(app.report.removed_lines, 0)
            self.assertEqual(str(app.apply["state"]), "normal")
            app.apply.invoke()
            finish()
            self.assertEqual(backup.read_bytes(), original + new)
            self.assertEqual(path.read_bytes(), kept + new)

            # Key controls stay visible at the minimum window dimensions.
            root.geometry("860x760")
            root.update()
            self.assertLess(app.apply.winfo_rooty() + app.apply.winfo_height(),
                            root.winfo_rooty() + root.winfo_height())


if __name__ == "__main__":
    unittest.main()
