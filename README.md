# EQLog

A small desktop log cleaner for EverQuest Legends, styled with the Companion
app's charcoal backgrounds, muted gold accents, and Segoe UI typography.

## Download for Windows

**[Download EQLog v0.1.0 — Windows installer (64-bit)](https://github.com/cadetmedia/eqlog/releases/download/v0.1.0/eqlog-Setup-0.1.0.exe)**

[Release details](https://github.com/cadetmedia/eqlog/releases/tag/v0.1.0) ·
[SHA-256 checksum](https://github.com/cadetmedia/eqlog/releases/download/v0.1.0/eqlog-Setup-0.1.0.exe.sha256)

Requires **Windows 10 or 11, 64-bit**. Python and administrator access are not
required. The current installer is unsigned.

### Install and clean your log

1. Close **EverQuest Legends** and **EverQuest Companion**.
2. Download and double-click `eqlog-Setup-0.1.0.exe`. It installs for your Windows
   account and creates Desktop and Start menu shortcuts.
3. Open **EQLog** and click **OK** to confirm both other apps are closed. Keep
   them closed until cleanup finishes.
4. Click **Browse** and choose your character's `eqlog_<character>_<server>.txt`
   from the game's `Logs` folder.
5. Click **Analyze log** to preview the savings without changing the file.
6. Click **Back up & clean**. EQLog verifies the original backup before replacing
   the working log. Later cleanups add new data to that same original backup.
7. When cleanup completes, reopen EverQuest and Companion.

Keep the `.original-backup.txt.bak` backup and `.eqlog-state.json` tracking file
beside your log. The backup preserves removed chat and the rest of the original
history through the latest backup update. Reduction depends on the amount of
chat; combat-heavy logs may shrink very little.

To uninstall, use **Windows Settings → Apps → EQLog → Uninstall**. User logs and
backups are preserved. See [Restore](#restore) for recovery directions.

## Run from source

Install Python 3.11 or newer with Tcl/Tk (included in the standard Windows Python
installer). From this checkout:

```sh
python -m eqlog
```

On Windows, you can also double-click `launch.pyw`.

1. Exit EverQuest **and Companion** before opening EQLog.
2. Read the startup warning and click **OK** to confirm both apps are closed.
   The main controls remain disabled until you confirm. Closing the warning
   instead exits EQLog.
3. Browse to `eqlog_<character>_<server>.txt` and click **Analyze log**.
4. Review the actual before/after sizes and click **Back up & clean**.
5. Restart Companion afterward to reload the log.

Analysis is read-only. The first cleanup creates a full sibling backup named
`eqlog_Bob_freeport.original-backup.txt.bak`. The `.bak` extension keeps Companion
from discovering it as another live `eqlog_*.txt` file.

On later cleanups, EQLog verifies the last cleaned file's identity and exact
byte prefix, then extends that **same original backup** with only the bytes
appended since the last backup. Earlier chat and other removed entries remain
in the backup forever. Identical new entries are preserved as new entries;
repeating cleanup without new data does not duplicate history. Backups update
when you clean, not continuously while you play.

The `.eqlog-state.json` file beside the live log tracks checksums, file identities
and append boundaries. Keep it with the original backup. A small `.eqlog-lock`
file prevents simultaneous cleanups and can remain on disk between runs.
EQLog verifies backup contents with SHA-256 and builds the extended backup in a
temporary file, then atomically replaces the backup before replacing the live
log. It never appends directly into the only recovery copy. Transaction state
allows a retry after interruption before or after either replacement without
adding the same data twice. Temporary files from a force-killed process may
remain on disk; they are not the original backup and are not used on retry.

If the live log was truncated, edited, restored, or replaced, or the backup or
tracking file is missing/corrupt, cleanup stops rather than guessing an append
boundary. Keep all files for recovery. Older timestamped backups from the first
version are left untouched; the new cumulative backup starts with the current
log on its first run and does not automatically merge those older snapshots.

**Do not clean while either application is running or start them during
cleanup.** Windows opens the source with write sharing denied. Linux uses an
advisory lock; unrelated writers need not honor that lock. Change detection is
an additional guard, not support for concurrent editing. Known EverQuest
process names are checked; the checkbox also covers unrecognized/Wine processes
and Companion. Atomic replacement creates a new filesystem file: byte content
and ordinary permission bits are preserved, but custom ACLs, alternate streams,
and other extended metadata are not copied.

## What this version removes

The conservative profile removes ordinary quoted chat (including channels,
tells, auctions, shouts and NPC speech) and blank lines. It explicitly retains:

- Pet ownership tells, all six recognized pet responses, and pet leader replies.
- Other members' group chat, because Companion uses it as membership evidence.
- Combat, loot, item transactions, spells, buffs, progression and system messages.
- All `/who` rows, unknown messages, malformed lines, and unfinished last lines.
- The first original line of every timestamp run, even if it is chat, because
  unknown events also advance Companion's timers and launch-epoch detector.

Retained lines stay byte-for-byte identical and in order, including line endings
and non-UTF-8 characters. Files stream through memory, rather than loading a
multi-gigabyte log at once. Companion's line sequence numbers will change.

Compatibility reference: upstream Companion commit
[`af7a938a06fe3b028c15f55007758d0a4b64b6ef`](https://github.com/jmoyers/everquest-companion/tree/af7a938a06fe3b028c15f55007758d0a4b64b6ef/engine/crates/eqlog/src/parse).
This is an independently implemented conservative filter, not the Companion
parser. Full Companion replay equivalence has **not** been verified. Custom
alerts or searches using removed chat lose that input; do not clean logs you
need for those features. Review new Companion parser releases before assuming
this profile still applies. Unknown messages remain because the spell database
and future features can give them meaning.

Reduction depends on the log: chat-heavy logs can shrink; combat-heavy logs
may shrink very little. The preview measures the savings. Keeping a full backup
means total disk usage initially **increases**, even though the working log is
smaller. For an update, allow free space for a full extended backup plus the
cleaned log; this can exceed two live-log sizes as the archive grows.

## Restore

Close EverQuest and Companion. Preserve the cleaned log separately if desired,
then copy the **verified** backup over the original filename. Restart Companion
to reload. The backup includes all original data through the latest backup
update, including chat removed by every cleanup. Logs written after that update
are still only in the live file: preserve that file before restoring.

Restoring is for recovery. EQLog will stop if it detects a restored/replaced log
rather than re-importing old history as new data. Keep the archive and tracking
files intact; use a separate live-log filename to start a new cleanup history.
Backups contain the original private chat; keep them private.

## Command line

```sh
python -m eqlog "path/to/eqlog_Bob_freeport.txt"
python -m eqlog "path/to/eqlog_Bob_freeport.txt" --apply --offline
python -m unittest discover -s tests -v
```

With a path, the default command previews without changing files and prints a
JSON report. `--apply --offline` creates or extends the original backup, then
cleans the file. The flag is the CLI equivalent of confirming both apps are closed.

## Windows installer

The Windows package is a one-click, per-user **NSIS** installer, matching
Companion's installation style. It bundles Python and Tcl/Tk, so end users do not
need Python, pip, or administrator access.

- Installs under `%LOCALAPPDATA%\Programs\EQLog`.
- Adds Desktop and Start menu shortcuts and a Windows Apps uninstall entry.
- Launches EQLog after interactive installation; `/S` installs silently.
- Uninstall removes only shipped files, shortcuts, and registration. User logs,
  cumulative backups, and tracking files are not uninstall targets, even if a
  user has placed them inside the installation folder.
- Updates are installed by running a newer installer. Automatic updating and
  Authenticode code signing are not configured. Current installers are unsigned.

### Build on Windows

Use Windows 10/11 x64, Python **3.12.10 x64** with Tcl/Tk, and **NSIS 3.11**.
From the checkout in PowerShell:

```powershell
py -3.12 -m venv .build-venv
.build-venv\Scripts\python -m pip install --require-hashes -r requirements-build.txt
.build-venv\Scripts\python -m unittest discover -s tests -v
.build-venv\Scripts\python scripts/build_windows.py
```

The build freezes the app using PyInstaller, runs its bundled-runtime smoke test
(including cumulative backup checks), then compiles the installer and writes:

```text
release/eqlog-Setup-0.1.0.exe
release/eqlog-Setup-0.1.0.exe.sha256
```

Version numbers come from `pyproject.toml`. The installer, app version resources,
and output filename use the same version. The build dependencies are pinned
with PyPI-verified SHA-256 hashes. Runtime dependencies, Python/Tcl/Tk licenses,
and the app's license ship in the payload. Logs and test fixtures are excluded.

On a **disposable Windows test machine** without EQLog already installed, run
`python scripts/test_installer.py` after building to verify silent installation,
installed-app backup behavior, Windows uninstall registration, and preservation
of a user-created backup during uninstall. Do not run this integration script
on a machine containing an existing EQLog installation.

### Automated Windows build

`.github/workflows/windows-installer.yml` runs unit/UI tests, builds the installer,
checks install/uninstall on Windows Server 2022, and uploads the installer,
checksum, and smoke-test reports as workflow artifacts. It supports manual
**Run workflow**, version tags (`v*`), and relevant pull requests. Version tags
publish the tested installer and checksum to GitHub Releases only after the
Windows build and install/uninstall checks pass. Manual and pull-request runs
produce workflow artifacts without publishing a release. User logs are never
uploaded.
