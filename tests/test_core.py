from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from eqlog.core import SafetyError, clean, preview, removal_reason, PET_SAYS

STAMP = b"[Fri Nov 13 12:00:00 2026] "


def line(text):
    return STAMP + text + b"\r\n"


class FilterTests(unittest.TestCase):
    def test_ordinary_chat(self):
        for text in [b"Bob says, 'hello'", b"You tell General:1, 'selling'",
                     b"Bob tells you, 'hello'", b"You told Bob, 'hi'",
                     b"Bob auctions, 'selling'", b"a rat says, 'go away'",
                     b"You tell your party, 'hello'", b"Bob says out of character, 'hi'"]:
            with self.subTest(text=text):
                self.assertEqual(removal_reason(line(text)), "Ordinary chat")

    def test_pet_and_group_evidence(self):
        examples = [b"Vebarn told you, 'Attacking a rat Master.'",
                    b"Vebarn told you, 'I am unable to wake a rat, Master.'",
                    b"Vebarn says, 'My leader is Bob.'", b"Bob tells the group, 'hello'"]
        examples += [b"a large spider says, '" + text + b"'" for text in PET_SAYS]
        for text in examples:
            with self.subTest(text=text):
                self.assertIsNone(removal_reason(line(text)))

    def test_mechanical_and_unknown_messages(self):
        examples = [
            b"You slash a rat for 12 points of damage. (Critical)",
            b"a rat resisted your Flame!", b"You gain a rune for 100 points of absorption.",
            b"Bob healed You for 20 hit points by Heal.",
            b"--You have looted a Fine Steel Sword from a rat's corpse.--",
            b"You received 10 platinum.", b"You have gained a level! Welcome to level 3!",
            b"You have completed achievement: Primary Class Unlock - Cleric",
            b"Bob has joined the group.", b"You have entered Freeport.",
            b"Welcome to EverQuest Legends!", b"You begin casting Gate.",
            b"Your illusion fades.", b"Your pet's Haste spell has worn off.",
            b"A thunder spirit princess staggers.", b"Your hands glow blue.",
            b"Your Sword feels alive with power.", b"You coat your blades in cobra venom.",
            b"[50 CLR/WAR] Bob (Human) ZONE: Freeport",
            b"Outputfile Complete: Bob-Inventory.txt", b"A new unknown system message.",
        ]
        for text in examples:
            with self.subTest(text=text):
                self.assertIsNone(removal_reason(line(text)))

    def test_malformed_and_partial_lines_are_retained(self):
        for value in [b"Bob says, 'hi'\n", STAMP + b"Bob says, 'hi'", b"\xff\xfe\x00\n"]:
            self.assertIsNone(removal_reason(value))


class FileTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "eqlog_Bob_freeport.txt"
        self.kept = line(b"You have entered Freeport.") + line(b"Your hands glow \xe9blue.")
        self.original = self.kept + line(b"Bob says, 'hello'") + b"\r\n" + b"partial"
        self.path.write_bytes(self.original)

    def test_preview_is_read_only_and_counts_bytes(self):
        report = preview(self.path)
        self.assertEqual(self.path.read_bytes(), self.original)
        self.assertEqual(report.removed_lines, 2)
        self.assertEqual(report.cleaned_bytes, len(self.kept + b"partial"))
        self.assertEqual(list(self.path.parent.iterdir()), [self.path])

    def test_backup_is_exact_and_output_is_byte_preserving(self):
        report = clean(self.path, offline=True, expected_sha256=preview(self.path).sha256)
        self.assertEqual(report.backup.read_bytes(), self.original)
        self.assertIn(".original-backup", report.backup.name)
        self.assertEqual(self.path.read_bytes(), self.kept + b"partial")
        self.assertEqual(report.original_bytes - report.cleaned_bytes, report.saved_bytes)

    def test_cleanup_is_idempotent_and_reuses_original_backup(self):
        first = clean(self.path, offline=True)
        second = clean(self.path, offline=True)
        self.assertEqual(first.backup, second.backup)
        self.assertEqual(first.backup.read_bytes(), self.original)
        self.assertEqual(second.removed_lines, 0)

    def test_requires_offline_confirmation(self):
        with self.assertRaises(SafetyError):
            clean(self.path)
        self.assertEqual(self.path.read_bytes(), self.original)

    def test_running_game_blocks_cleanup(self):
        with patch("eqlog.core._check_game_closed", side_effect=SafetyError("running")):
            with self.assertRaises(SafetyError):
                clean(self.path, offline=True)
        self.assertEqual(len(list(self.path.parent.iterdir())), 1)

    def test_stale_preview_blocks_replacement(self):
        report = preview(self.path)
        self.path.write_bytes(self.original + b"new bytes")
        with self.assertRaisesRegex(SafetyError, "changed since the preview"):
            clean(self.path, offline=True, expected_sha256=report.sha256)
        self.assertEqual(self.path.read_bytes(), self.original + b"new bytes")

    def test_backup_corruption_blocks_replacement(self):
        with patch("eqlog.core._hash_file", return_value="incorrect"):
            with self.assertRaisesRegex(SafetyError, "Backup verification failed"):
                clean(self.path, offline=True)
        self.assertEqual(self.path.read_bytes(), self.original)

    def test_write_failure_leaves_original_intact(self):
        with patch("eqlog.core._scan", side_effect=OSError("disk full")):
            with self.assertRaisesRegex(SafetyError, "disk full"):
                clean(self.path, offline=True)
        self.assertEqual(self.path.read_bytes(), self.original)
        self.assertFalse(list(self.path.parent.glob(".*.clean-*")))

    def test_replace_failure_retains_backup_and_original(self):
        with patch("eqlog.core._replace_live", side_effect=PermissionError("locked")):
            with self.assertRaisesRegex(SafetyError, "locked"):
                clean(self.path, offline=True)
        self.assertEqual(self.path.read_bytes(), self.original)
        self.assertEqual(next(self.path.parent.glob("*.original-backup.txt.bak")).read_bytes(), self.original)
        self.assertFalse(list(self.path.parent.glob(".*.clean-*")))

    def test_source_append_aborts_without_losing_new_bytes(self):
        from eqlog.core import _scan

        def append_during_scan(*args):
            with self.path.open("ab") as source:
                source.write(b"new entry")
            return _scan(*args)

        with patch("eqlog.core._scan", side_effect=append_during_scan):
            import os
            if os.name == "nt":
                # The Windows handle denies the competing writer before append.
                with self.assertRaises(SafetyError):
                    clean(self.path, offline=True)
            else:
                with self.assertRaisesRegex(SafetyError, "changed during cleanup"):
                    clean(self.path, offline=True)
        self.assertEqual(self.path.read_bytes(), self.original if os.name == "nt"
                         else self.original + b"new entry")

    def test_preserves_clock_progression_from_chat(self):
        other = b"[Fri Nov 13 12:01:00 2026] Bob says, 'hi'\n"
        self.path.write_bytes(self.kept + other + other)
        clean(self.path, offline=True)
        self.assertEqual(self.path.read_bytes(), self.kept + other)

    def test_empty_file(self):
        self.path.write_bytes(b"")
        report = clean(self.path, offline=True)
        self.assertEqual(report.reduction, 0)
        self.assertEqual(report.backup.read_bytes(), b"")

    def test_symlink_rejected(self):
        link = self.path.parent / "link.txt"
        try:
            link.symlink_to(self.path)
        except OSError:
            self.skipTest("Symlinks unavailable")
        if not link.exists() and not link.is_symlink():
            self.skipTest("Host did not create the requested symlink (unsupported under Wine)")
        with self.assertRaises(SafetyError):
            clean(link, offline=True)


if __name__ == "__main__":
    unittest.main()
