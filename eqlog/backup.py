"""Crash-recoverable cumulative backup transactions.

The sidecar records both possible live-file versions. A prepared transaction also
records the previous archive state, so retries can distinguish an archive rename
that completed from one that did not. No suffix is inferred from timestamps.
"""
from contextlib import contextmanager
import hashlib
import json
import os
from pathlib import Path
import stat
import tempfile


def fingerprint(path):
    with Path(path).open("rb") as file:
        return {"size": os.fstat(file.fileno()).st_size,
                "sha256": hashlib.file_digest(file, "sha256").hexdigest()}


def sync_directory(path):
    if os.name != "nt":
        fd = os.open(path, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(fd)
        finally:
            os.close(fd)


def atomic_state(path, state):
    fd, temporary = tempfile.mkstemp(prefix=".eqlog-state-", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as file:
            json.dump(state, file, indent=2)
            file.write("\n")
            file.flush()
            os.fsync(file.fileno())
        os.replace(temporary, path)
        sync_directory(path.parent)
    finally:
        Path(temporary).unlink(missing_ok=True)


@contextmanager
def archive_lock(path):
    # This stable lock also serializes cleaners after the live file is replaced.
    if path.is_symlink():
        raise ValueError("The backup lock must not be a symbolic link.")
    fd = os.open(path, os.O_CREAT | os.O_RDWR | getattr(os, "O_NOFOLLOW", 0), 0o600)
    with os.fdopen(fd, "r+b", buffering=0) as file:
        if not stat.S_ISREG(os.fstat(file.fileno()).st_mode) or os.fstat(file.fileno()).st_nlink != 1:
            raise ValueError("Invalid backup lock file.")
        if os.name == "nt":
            import msvcrt
            msvcrt.locking(file.fileno(), msvcrt.LK_NBLCK, 1)
            try:
                yield
            finally:
                file.seek(0)
                msvcrt.locking(file.fileno(), msvcrt.LK_UNLCK, 1)
        else:
            import fcntl
            fcntl.flock(file, fcntl.LOCK_EX | fcntl.LOCK_NB)
            yield


def _valid_fingerprint(value):
    return (isinstance(value, dict) and type(value.get("size")) is int
            and value["size"] >= 0 and isinstance(value.get("sha256"), str)
            and len(value["sha256"]) == 64
            and all(c in "0123456789abcdef" for c in value["sha256"]))


def _valid_state(state):
    return (isinstance(state, dict) and state.get("version") == 1
            and all(_valid_fingerprint(state.get(key)) for key in ("archive", "before", "after"))
            and all(isinstance(state.get(key), list) and len(state[key]) == 2
                    and all(type(n) is int and n >= 0 for n in state[key])
                    for key in ("before_id", "after_id")))


def load_state(state_path, backup):
    for path in (state_path, backup):
        if path.is_symlink() or (path.exists() and
                (not path.is_file() or path.stat().st_nlink != 1)):
            raise ValueError("Backup and tracking files must be regular files, not links.")
    if not state_path.exists():
        if backup.exists():
            raise ValueError("The original backup exists but its tracking file is missing. "
                             "Keep both files and restore the tracking file before cleaning.")
        return None
    state = json.loads(state_path.read_text(encoding="utf-8"))
    if not _valid_state(state):
        raise ValueError("The backup tracking file is invalid. No files were cleaned.")
    actual = fingerprint(backup) if backup.exists() else None
    canonical = {key: state[key] for key in ("version", "archive", "before", "after", "before_id", "after_id")}
    if actual == state["archive"]:
        if "previous" in state:
            canonical["pending"] = True
        return canonical
    if "previous" in state:
        previous = state["previous"]
        if previous is None and actual is None:
            return None  # First transaction stopped before publishing its backup.
        if _valid_state(previous) and actual == previous["archive"]:
            return previous  # Archive rename had not happened; retry from old state.
    raise ValueError("The original backup is missing or has changed. "
                     "Cleanup stopped to protect the recoverable history.")


def suffix_offset(source, state):
    if state is None:
        return 0
    info = os.fstat(source.fileno())
    identity = [info.st_dev, info.st_ino]
    # Identical text can legitimately recur after a cleanup. File identity tells
    # us which side of an interrupted atomic rename we are on; choosing the
    # longest matching content prefix would silently lose those repeated bytes.
    if identity == state["after_id"]:
        candidate = state["after"]
    elif state.get("pending") and identity == state["before_id"]:
        candidate = state["before"]
    else:
        raise ValueError("The live log was replaced since the last cleanup. "
                         "No safe append boundary was found; the original backup is unchanged.")

    def matches(candidate):
        source.seek(0)
        remaining = candidate["size"]
        digest = hashlib.sha256()
        while remaining:
            chunk = source.read(min(1024 * 1024, remaining))
            if not chunk:
                break
            digest.update(chunk)
            remaining -= len(chunk)
        return not remaining and digest.hexdigest() == candidate["sha256"]

    if (candidate == state["after"] and state["archive"] != candidate
            and matches(state["archive"])):
        raise ValueError("The live log matches the full original backup, possibly after a restore. "
                         "No safe append boundary was found. Keep this restored log and backup; "
                         "use a separate log filename to start a new cleanup history.")
    if matches(candidate):
        return candidate["size"]
    raise ValueError("The live log was truncated, edited, or replaced since the last backup. "
                     "No safe append boundary was found; the original backup is unchanged.")


def stage_archive(backup, source, offset, state):
    fd, name = tempfile.mkstemp(prefix=".eqlog-backup-", dir=backup.parent)
    temporary = Path(name)
    digest = hashlib.sha256()
    try:
        with os.fdopen(fd, "wb") as output:
            if state is not None:
                with backup.open("rb") as old:
                    previous_digest = hashlib.sha256()
                    count = 0
                    while chunk := old.read(1024 * 1024):
                        output.write(chunk)
                        digest.update(chunk)
                        previous_digest.update(chunk)
                        count += len(chunk)
                if {"size": count, "sha256": previous_digest.hexdigest()} != state["archive"]:
                    raise ValueError("The original backup changed while it was being read.")
            source.seek(offset)
            while chunk := source.read(1024 * 1024):
                output.write(chunk)
                digest.update(chunk)
            output.flush()
            os.fsync(output.fileno())
        expected = {"size": temporary.stat().st_size, "sha256": digest.hexdigest()}
        if fingerprint(temporary) != expected:
            raise ValueError("Backup verification failed. The original log was not replaced.")
        return temporary, expected
    except BaseException:
        temporary.unlink(missing_ok=True)
        raise
