"""Build the bundled Windows app, exercise it, and produce an NSIS installer."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tomllib

ROOT = Path(__file__).resolve().parents[1]


def prepare():
    version = tomllib.loads((ROOT / "pyproject.toml").read_text())["project"]["version"]
    parts = tuple(map(int, version.split(".")))
    if len(parts) != 3:
        raise ValueError("Windows builds require a three-part numeric version")
    build = ROOT / "build" / "windows"
    build.mkdir(parents=True, exist_ok=True)
    (ROOT / "release").mkdir(exist_ok=True)
    info = f'''VSVersionInfo(
  ffi=FixedFileInfo(filevers={parts + (0,)}, prodvers={parts + (0,)},
    mask=0x3f, flags=0x0, OS=0x40004, fileType=0x1, subtype=0x0, date=(0, 0)),
  kids=[StringFileInfo([StringTable('040904B0', [
    StringStruct('ProductName', 'EQLog'),
    StringStruct('FileDescription', 'EverQuest Legends Log Cleaner'),
    StringStruct('FileVersion', '{version}'),
    StringStruct('ProductVersion', '{version}'),
    StringStruct('InternalName', 'EQLog'),
    StringStruct('OriginalFilename', 'EQLog.exe'),
    StringStruct('LegalCopyright', 'CC0 1.0 Universal')
  ])]), VarFileInfo([VarStruct('Translation', [1033, 1200])])]
)
'''
    (build / "version-info.txt").write_text(info, encoding="utf-8")
    return version, build


def uninstall_manifest(payload, destination):
    # Delete only files shipped by this build. Unknown user-created files, logs,
    # and backups inside the installation directory survive uninstall.
    def escape(path):
        return str(path).replace("/", "\\").replace("$", "$$").replace('"', '$\\"')

    files = sorted(p.relative_to(payload) for p in payload.rglob("*") if p.is_file())
    if not files or not (payload / "EQLog.exe").is_file():
        raise RuntimeError("The frozen EQLog payload is missing")
    dirs = sorted((p.relative_to(payload) for p in payload.rglob("*") if p.is_dir()),
                  key=lambda p: (len(p.parts), str(p)), reverse=True)
    lines = [f'Delete "$INSTDIR\\{escape(p)}"' for p in files]
    lines.extend(f'RMDir "$INSTDIR\\{escape(p)}"' for p in dirs)
    destination.write_text("\n".join(lines) + "\n", encoding="utf-8")


def smoke(executable, result):
    result.unlink(missing_ok=True)
    subprocess.run([str(executable), "--smoke-test", str(result)], check=True, timeout=120)
    data = json.loads(result.read_text(encoding="utf-8"))
    if not data.get("ok"):
        raise RuntimeError(f"Packaged app failed its self-test: {data}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--freeze-only", action="store_true", help="Freeze and smoke-test; compile NSIS separately")
    args = parser.parse_args()
    if sys.platform != "win32":
        parser.error("Run this with Windows Python (native Windows or Wine)")
    os.chdir(ROOT)
    version, build = prepare()
    subprocess.run([sys.executable, "-m", "PyInstaller", "--clean", "--noconfirm",
                    "windows/EQLog.spec"], check=True)
    payload = ROOT / "dist" / "EQLog"
    smoke(payload / "EQLog.exe", build / "frozen-smoke.json")
    uninstall_manifest(payload, build / "uninstall-files.nsh")
    if args.freeze_only:
        print("Frozen Windows application and smoke test complete.")
        return
    compiler = shutil.which("makensis")
    if not compiler:
        for base in (os.environ.get("ProgramFiles(x86)"), os.environ.get("ProgramFiles")):
            if base and (Path(base) / "NSIS" / "makensis.exe").is_file():
                compiler = str(Path(base) / "NSIS" / "makensis.exe")
                break
    if not compiler:
        raise RuntimeError("Install NSIS 3 and rerun the build")
    subprocess.run([compiler, f"/DAPP_VERSION={version}", f"/DPAYLOAD_DIR={payload}",
                    f"/DOUTPUT_DIR={ROOT / 'release'}",
                    f"/DUNINSTALL_INCLUDE={build / 'uninstall-files.nsh'}",
                    str(ROOT / "windows" / "installer.nsi")], check=True)
    installer = ROOT / "release" / f"eqlog-Setup-{version}.exe"
    digest = hashlib.file_digest(installer.open("rb"), "sha256").hexdigest()
    installer.with_suffix(".exe.sha256").write_text(f"{digest}  {installer.name}\n", encoding="ascii")
    print(f"Installer built: {installer}")


if __name__ == "__main__":
    main()
