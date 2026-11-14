"""Install/uninstall integration test. Run only on a disposable Windows machine."""
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import tomllib

ROOT = Path(__file__).resolve().parents[1]


def main():
    if sys.platform != "win32":
        raise RuntimeError("Installer testing requires Windows or Wine")
    import winreg
    version = tomllib.loads((ROOT / "pyproject.toml").read_text())["project"]["version"]
    installer = ROOT / "release" / f"eqlog-Setup-{version}.exe"
    installed = Path(os.environ["LOCALAPPDATA"]) / "Programs" / "EQLog"
    key = r"Software\Microsoft\Windows\CurrentVersion\Uninstall\cadetmedia.EQLog"
    if installed.exists():
        raise RuntimeError("Use a fresh disposable machine: the installation folder already exists")
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, key):
            raise RuntimeError("An EQLog uninstall entry already exists; refusing to replace a user's installation")
    except FileNotFoundError:
        pass
    subprocess.run([str(installer), "/S"], check=True, timeout=120)
    executable = installed / "EQLog.exe"
    if not executable.is_file():
        raise RuntimeError("The installed executable is missing")
    result = ROOT / "build" / "windows" / "installed-smoke.json"
    result.unlink(missing_ok=True)
    subprocess.run([str(executable), "--smoke-test", str(result)], check=True, timeout=120)
    if not json.loads(result.read_text(encoding="utf-8"))["ok"]:
        raise RuntimeError("Installed-app smoke test failed")
    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, key) as registration:
        if winreg.QueryValueEx(registration, "DisplayVersion")[0] != version:
            raise RuntimeError("Installer version registration is incorrect")
    import ctypes
    from ctypes import wintypes
    get_folder = ctypes.WinDLL("shell32").SHGetFolderPathW
    get_folder.argtypes = [wintypes.HWND, ctypes.c_int, wintypes.HANDLE,
                          wintypes.DWORD, wintypes.LPWSTR]
    get_folder.restype = ctypes.c_long
    shortcuts = []
    for folder_id in (0x10, 0x02):  # Current user's Desktop and Start Menu Programs.
        buffer = ctypes.create_unicode_buffer(260)
        if get_folder(None, folder_id, None, 0, buffer) != 0:
            raise RuntimeError("Could not locate the shortcut directory")
        shortcut = Path(buffer.value) / "EQLog.lnk"
        if not shortcut.is_file():
            raise RuntimeError(f"Installer shortcut is missing: {shortcut}")
        shortcuts.append(shortcut)
    # Uninstaller must not recursively delete unknown files in either directory.
    sentinels = [installed / "eqlog_user.original-backup.txt.bak",
                 installed / "_internal" / "user-backup.txt.bak"]
    for sentinel in sentinels:
        sentinel.write_bytes(b"keep original player log\r\n")
    subprocess.run([str(installed / "Uninstall EQLog.exe"), "/S"], check=True, timeout=120)
    # NSIS launches a temporary uninstaller child and the original process may
    # exit first. Wait for the whole removal sequence, not just its first file.
    def registered():
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, key):
                return True
        except FileNotFoundError:
            return False

    deadline = time.monotonic() + 30
    while (executable.exists() or any(p.exists() for p in shortcuts) or registered()) and time.monotonic() < deadline:
        time.sleep(0.2)
    if executable.exists():
        raise RuntimeError("Uninstall did not remove the executable")
    for sentinel in sentinels:
        if sentinel.read_bytes() != b"keep original player log\r\n":
            raise RuntimeError("Uninstall removed or changed a user backup")
    if any(p.exists() for p in shortcuts):
        raise RuntimeError("Uninstall did not remove the shortcuts")
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, key):
            raise RuntimeError("Uninstall registration was not removed")
    except FileNotFoundError:
        pass
    result.with_name("installer-integration.json").write_text(json.dumps({
        "ok": True, "install": True, "installed_runtime": True,
        "shortcuts": True, "uninstall": True, "user_backups_preserved": True,
    }, indent=2) + "\n", encoding="utf-8")
    print("Install, bundled runtime, shortcuts and safe uninstall checks passed.")


if __name__ == "__main__":
    main()
