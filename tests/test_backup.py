import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from eqlog import core
from eqlog.core import clean, SafetyError


def entry(body):
    return b"[Fri Nov 13 12:00:00 2026] " + body + b"\r\n"


class CumulativeBackupTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "eqlog_Bob_freeport.txt"
        self.original = entry(b"You have entered Freeport.") + entry(b"Bob says, 'old chat'")
        self.path.write_bytes(self.original)
        self.backup = self.path.with_name("eqlog_Bob_freeport.original-backup.txt.bak")
        self.state = self.path.with_name(self.path.name + ".eqlog-state.json")

    def append(self, data):
        with self.path.open("ab") as log:
            log.write(data)

    def test_multiple_cleanups_keep_all_original_history_once(self):
        clean(self.path, offline=True)
        newer = entry(b"Bob says, 'new chat'") + entry(b"You gain experience!")
        self.append(newer)
        clean(self.path, offline=True)
        self.assertEqual(self.backup.read_bytes(), self.original + newer)
        self.assertNotIn(b"new chat", self.path.read_bytes())
        clean(self.path, offline=True)
        self.assertEqual(self.backup.read_bytes(), self.original + newer)
        self.assertEqual(len(list(self.path.parent.glob("*.original-backup.txt.bak"))), 1)

    def test_identical_new_bytes_are_not_mistaken_for_duplicates(self):
        clean(self.path, offline=True)
        data = entry(b"Bob says, 'repeat'") * 2
        self.append(data)
        clean(self.path, offline=True)
        self.append(data)
        clean(self.path, offline=True)
        self.assertEqual(self.backup.read_bytes(), self.original + data + data)

    def test_partial_line_can_be_completed_on_next_run(self):
        self.path.write_bytes(self.original + b"incomplete")
        clean(self.path, offline=True)
        self.append(b" now complete\r\n")
        clean(self.path, offline=True)
        self.assertEqual(self.backup.read_bytes(), self.original + b"incomplete now complete\r\n")

    def test_edits_and_truncation_abort_without_changing_backup(self):
        clean(self.path, offline=True)
        for contents in (b"", b"unrelated replacement", self.original.replace(b"Freeport", b"Qeynos")):
            self.path.write_bytes(contents)
            with self.assertRaisesRegex(SafetyError, "No safe append boundary"):
                clean(self.path, offline=True)
            self.assertEqual(self.path.read_bytes(), contents)
            self.assertEqual(self.backup.read_bytes(), self.original)

    def test_missing_or_corrupt_archive_is_not_silently_rebuilt(self):
        clean(self.path, offline=True)
        live = self.path.read_bytes()
        for contents in (None, b"corrupt"):
            if contents is None:
                self.backup.unlink()
            else:
                self.backup.write_bytes(contents)
            with self.assertRaisesRegex(SafetyError, "backup is missing or has changed"):
                clean(self.path, offline=True)
            self.assertEqual(self.path.read_bytes(), live)

    def test_missing_tracking_file_preserves_archive(self):
        clean(self.path, offline=True)
        self.state.unlink()
        with self.assertRaisesRegex(SafetyError, "tracking file is missing"):
            clean(self.path, offline=True)
        self.assertEqual(self.backup.read_bytes(), self.original)

    def test_malformed_tracking_file_blocks_cleanup(self):
        clean(self.path, offline=True)
        self.state.write_text('{"version": 1}')
        with self.assertRaisesRegex(SafetyError, "tracking file is invalid"):
            clean(self.path, offline=True)
        self.assertEqual(self.backup.read_bytes(), self.original)

    def test_restored_original_is_not_mistaken_for_new_data(self):
        clean(self.path, offline=True)
        new = entry(b"Bob says, 'later'")
        self.append(new)
        clean(self.path, offline=True)
        self.path.write_bytes(self.backup.read_bytes())
        with self.assertRaisesRegex(SafetyError, "possibly after a restore"):
            clean(self.path, offline=True)
        self.assertEqual(self.backup.read_bytes(), self.original + new)

    def test_retry_after_archive_published_but_live_replace_fails(self):
        clean(self.path, offline=True)
        new = entry(b"Bob says, 'new'")
        self.append(new)
        before = self.path.read_bytes()
        with patch("eqlog.core._replace_live", side_effect=PermissionError("live rename failed")):
            with self.assertRaises(SafetyError):
                clean(self.path, offline=True)
        self.assertEqual(self.path.read_bytes(), before)
        self.assertEqual(self.backup.read_bytes(), self.original + new)
        extra = entry(b"Bob says, 'after failure'")
        self.append(extra)
        clean(self.path, offline=True)
        self.assertEqual(self.backup.read_bytes(), self.original + new + extra)

    def test_retry_when_archive_rename_did_not_happen(self):
        clean(self.path, offline=True)
        new = entry(b"Bob says, 'new'")
        self.append(new)
        replace = os.replace

        def fail_archive(source, destination):
            if Path(destination) == self.backup:
                raise OSError("archive rename failed")
            return replace(source, destination)

        with patch("eqlog.core.os.replace", side_effect=fail_archive):
            with self.assertRaises(SafetyError):
                clean(self.path, offline=True)
        self.assertEqual(self.backup.read_bytes(), self.original)
        clean(self.path, offline=True)
        self.assertEqual(self.backup.read_bytes(), self.original + new)

    def test_first_backup_rename_failure_can_be_retried(self):
        replace = os.replace

        def fail_archive(source, destination):
            if Path(destination) == self.backup:
                raise OSError("archive rename failed")
            return replace(source, destination)

        with patch("eqlog.core.os.replace", side_effect=fail_archive):
            with self.assertRaises(SafetyError):
                clean(self.path, offline=True)
        self.assertFalse(self.backup.exists())
        self.assertEqual(self.path.read_bytes(), self.original)
        clean(self.path, offline=True)
        self.assertEqual(self.backup.read_bytes(), self.original)

    def test_retry_after_live_replaced_but_final_state_write_fails(self):
        clean(self.path, offline=True)
        new = entry(b"Bob says, 'new'")
        self.append(new)
        save = core.atomic_state

        def fail_finalize(path, state):
            if "previous" not in state:
                raise OSError("state write failed")
            save(path, state)

        with patch("eqlog.core.atomic_state", side_effect=fail_finalize):
            with self.assertRaises(SafetyError):
                clean(self.path, offline=True)
        self.assertEqual(self.backup.read_bytes(), self.original + new)
        self.assertNotIn(b"new", self.path.read_bytes())
        clean(self.path, offline=True)
        self.assertEqual(self.backup.read_bytes(), self.original + new)
        self.assertNotIn("previous", json.loads(self.state.read_text()))

    def test_state_write_failure_leaves_archive_and_live_untouched(self):
        clean(self.path, offline=True)
        self.append(entry(b"Bob says, 'new'"))
        before = self.path.read_bytes()
        with patch("eqlog.core.atomic_state", side_effect=OSError("disk full")):
            with self.assertRaisesRegex(SafetyError, "disk full"):
                clean(self.path, offline=True)
        self.assertEqual(self.path.read_bytes(), before)
        self.assertEqual(self.backup.read_bytes(), self.original)

    def test_original_backup_cannot_be_selected_for_cleanup(self):
        clean(self.path, offline=True)
        with self.assertRaisesRegex(SafetyError, "Select the live log"):
            clean(self.backup, offline=True)
        self.assertEqual(self.backup.read_bytes(), self.original)


if __name__ == "__main__":
    unittest.main()
