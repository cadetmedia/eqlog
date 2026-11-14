"""Streaming, byte-preserving cleanup. Unknown messages are deliberately retained."""
from __future__ import annotations

from collections import Counter
from contextlib import contextmanager
from dataclasses import dataclass
import hashlib
import os
from pathlib import Path
import re
import stat
import subprocess
import tempfile


from .backup import (archive_lock, atomic_state, fingerprint, load_state,
                     stage_archive, suffix_offset, sync_directory)


class SafetyError(Exception):
    """The log cannot safely be changed."""


# Independently implemented from the upstream parser's accepted message shapes.
# Keep group chat: its speaker is used as group-membership evidence by Companion.
PET_SAYS = {
    b"Following you, Master.", b"Now regrouping, master.",
    b"Sorry, Master... calming down.",
    b"Now holding, Master.  I will not start new attacks until ordered.",
    b"As you wish, oh great one.",
    b"I beg forgiveness, Master.  That is not a legal target.",
}
STAMP = re.compile(rb"^\[[^\]\r\n]+\] ?(.*)$")
CHAT = re.compile(
    rb"^(?:You|.+?) (?:say|says|say out of character|says out of character|"
    rb"shout|shouts|auction|auctions|tell|tells|told)(?: [^\r\n]*?)?, '.*'$"
)
PET_TELL = re.compile(
    rb"^.+? told you, '(?:Attacking .+ Master|I am unable to wake .+?, Master)\.'$"
)
GROUP = re.compile(rb"^[A-Za-z][A-Za-z`'-]* tells the group, '")
SAY = re.compile(rb"^.+? says, '(.*)'$")


def removal_reason(line: bytes) -> str | None:
    """Only discard known nonmechanical text. Preserve original bytes otherwise."""
    # An unfinished line may still be being written: never discard it.
    if not line.endswith(b"\n"):
        return None
    body = line.rstrip(b"\r\n")
    if not body.strip():
        return "Blank lines"
    match = STAMP.fullmatch(body)
    if not match:
        return None
    text = match[1]
    # Preserve any shape that the parser can consume, even before testing chat.
    if PET_TELL.fullmatch(text) or GROUP.match(text):
        return None
    say = SAY.fullmatch(text)
    if say and (say[1] in PET_SAYS or re.fullmatch(rb"My leader is .+\.", say[1])):
        return None
    # Database-backed spell messages and future system events remain untouched.
    if CHAT.fullmatch(text):
        return "Ordinary chat"
    return None


@dataclass
class Report:
    path: Path
    original_bytes: int
    cleaned_bytes: int
    total_lines: int
    removed_lines: int
    reasons: dict[str, int]
    sha256: str
    backup: Path | None = None

    @property
    def saved_bytes(self):
        return self.original_bytes - self.cleaned_bytes

    @property
    def reduction(self):
        return 100 * self.saved_bytes / self.original_bytes if self.original_bytes else 0


def _scan(source, path, destination=None):
    digest = hashlib.sha256()
    before = after = total = removed = 0
    reasons = Counter()
    previous_stamp = None
    for line in source:
        digest.update(line)
        before += len(line)
        total += 1
        reason = removal_reason(line)
        # Even unknown events advance Companion's timers and epoch detection.
        # Keep the first line of EVERY timestamp run, preserving its exact clock
        # progression rather than silently stretching idle fights or buff timers.
        stamp = re.match(rb"^\[([^\]\r\n]+)\]", line)
        if stamp:
            if stamp[1] != previous_stamp:
                reason = None
            previous_stamp = stamp[1]
        if reason:
            removed += 1
            reasons[reason] += 1
        else:
            after += len(line)
            if destination is not None:
                destination.write(line)
    return Report(path, before, after, total, removed, dict(reasons), digest.hexdigest())


def _identity(info):
    # Windows st_ctime is deprecated and can mean creation time in stat() but
    # change time in fstat(). Use the explicit birth time (Python 3.12+) there.
    extra_time = getattr(info, "st_birthtime_ns", None) if os.name == "nt" else info.st_ctime_ns
    return info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns, extra_time


def _check_path(path):
    path = Path(os.path.abspath(path))
    if path.is_symlink() or not stat.S_ISREG(path.lstat().st_mode):
        raise SafetyError("Choose a regular log file, not a link or directory.")
    if path.stat().st_nlink != 1:
        raise SafetyError("Hard-linked log files cannot be cleaned safely.")
    return path


def preview(path):
    path = _check_path(path)
    with path.open("rb") as source:
        initial = _identity(os.fstat(source.fileno()))
        result = _scan(source, path)
        if initial != _identity(os.fstat(source.fileno())) or initial != _identity(path.stat()):
            raise SafetyError("The log changed during analysis. Close EverQuest and try again.")
    return result


def _check_game_closed():
    if os.name == "nt":
        import csv
        output = subprocess.run(
            ["tasklist", "/FO", "CSV", "/NH"], capture_output=True, text=True,
            check=True, creationflags=subprocess.CREATE_NO_WINDOW,
        ).stdout
        names = [row[0].lower() for row in csv.reader(output.splitlines()) if row]
    else:
        names = []
        for proc in Path("/proc").glob("[0-9]*/comm"):
            try:
                names.append(proc.read_text().strip().lower())
            except FileNotFoundError:
                pass
        # Non-Linux hosts rely on the explicit offline acknowledgement.
    if any(name in {"eqgame", "eqgame.exe", "everquest.exe"} for name in names):
        raise SafetyError("EverQuest is running. Exit the game before cleaning the log.")


@contextmanager
def _locked_source(path):
    if os.name == "nt":
        # Deny new writers and fail if a writer is already open. DELETE sharing
        # permits our atomic replacement while the read handle remains open.
        import ctypes
        from ctypes import wintypes
        import msvcrt
        kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        create = kernel.CreateFileW
        create.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD,
                           wintypes.LPVOID, wintypes.DWORD, wintypes.DWORD, wintypes.HANDLE]
        create.restype = wintypes.HANDLE
        handle = create(str(path), 0x80000000, 1 | 4, None, 3, 0x80, None)
        if handle == wintypes.HANDLE(-1).value:
            raise SafetyError("Cannot lock the log. Close EverQuest and Companion, then retry.")
        try:
            fd = msvcrt.open_osfhandle(handle, os.O_RDONLY | os.O_BINARY)
        except Exception:
            close = kernel.CloseHandle
            close.argtypes = [wintypes.HANDLE]
            close(handle)
            raise
        with os.fdopen(fd, "rb") as source:
            yield source
    else:
        import fcntl
        with path.open("rb") as source:
            try:
                fcntl.flock(source, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError as exc:
                raise SafetyError("Another cleaner has locked this file.") from exc
            yield source


def _hash_file(path):
    with Path(path).open("rb") as source:
        return hashlib.file_digest(source, "sha256").hexdigest()


def _replace_live(replacement, path):
    if os.name != "nt":
        os.replace(replacement, path)
        return
    # MoveFileEx (os.replace) can fail against an open destination even with
    # DELETE sharing. ReplaceFile is designed for replacing a protected file;
    # retain our deny-writers handle throughout the transaction.
    import ctypes
    from ctypes import wintypes
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    replace = kernel.ReplaceFileW
    replace.argtypes = [wintypes.LPCWSTR, wintypes.LPCWSTR, wintypes.LPCWSTR,
                        wintypes.DWORD, wintypes.LPVOID, wintypes.LPVOID]
    replace.restype = wintypes.BOOL
    if not replace(str(path), str(replacement), None, 0, None, None):
        raise ctypes.WinError(ctypes.get_last_error())


def clean(path, *, offline=False, expected_sha256=None):
    """Extend the original archive, verify it, then replace the offline live log."""
    if not offline:
        raise SafetyError("Close EverQuest and Companion and confirm they are closed first.")
    path = _check_path(path)
    if (".original-backup" in path.name.lower()
            or path.name.lower().endswith((".bak", ".eqlog-state.json", ".eqlog-lock"))):
        raise SafetyError("Select the live log, not a backup or tracking file.")
    _check_game_closed()
    backup = path.with_name(f"{path.stem}.original-backup{path.suffix}.bak")
    state_path = path.with_name(f"{path.name}.eqlog-state.json")
    lock_path = path.with_name(f"{path.name}.eqlog-lock")
    temporary = None
    staged_backup = None
    try:
        with archive_lock(lock_path), _locked_source(path) as source:
            info = os.fstat(source.fileno())
            initial = _identity(info)
            if initial != _identity(path.stat()):
                raise SafetyError("The selected file was replaced. Analyze it again.")
            state = load_state(state_path, backup)
            offset = suffix_offset(source, state)
            source.seek(0)
            fd, temporary = tempfile.mkstemp(prefix=f".{path.name}.clean-", dir=path.parent)
            with os.fdopen(fd, "wb") as output:
                report = _scan(source, path, output)
                output.flush()
                os.fsync(output.fileno())
            checksum = report.sha256
            if expected_sha256 is not None and checksum != expected_sha256:
                raise SafetyError("The log changed since the preview. Analyze it again.")
            staged_backup, archive_info = stage_archive(backup, source, offset, state)
            if _hash_file(staged_backup) != archive_info["sha256"]:
                raise SafetyError("Backup verification failed. The original log was not replaced.")
            source.seek(0)
            if hashlib.file_digest(source, "sha256").hexdigest() != checksum:
                raise SafetyError("The log changed during cleanup. The original was not replaced.")
            _check_game_closed()
            if initial != _identity(os.fstat(source.fileno())) or initial != _identity(path.stat()):
                raise SafetyError("The log changed during cleanup. The original was not replaced.")
            os.chmod(temporary, stat.S_IMODE(info.st_mode))
            new_state = {
                "version": 1,
                "archive": archive_info,
                "before": {"size": report.original_bytes, "sha256": checksum},
                "after": fingerprint(temporary),
                "before_id": [info.st_dev, info.st_ino],
                "after_id": ([os.stat(temporary).st_dev, os.stat(temporary).st_ino]
                             if report.removed_lines else [info.st_dev, info.st_ino]),
            }
            # Publish recovery information FIRST. A retry accepts either the old
            # archive or the new one, then either live-file version, without
            # duplicating new bytes after interruption at either rename.
            atomic_state(state_path, new_state | {"previous": state})
            os.replace(staged_backup, backup)
            staged_backup = None
            sync_directory(path.parent)
            if report.removed_lines:
                _replace_live(temporary, path)
                temporary = None
                sync_directory(path.parent)
            atomic_state(state_path, new_state)
            report.backup = backup
            return report
    except Exception as exc:
        raise SafetyError(f"{exc}\nOriginal backup location: {backup}\n"
                          "Keep the backup and .eqlog-state.json together. "
                          "Retrying can recover an interrupted cleanup.") from exc
    finally:
        if temporary is not None:
            Path(temporary).unlink(missing_ok=True)
        if staged_backup is not None:
            staged_backup.unlink(missing_ok=True)
