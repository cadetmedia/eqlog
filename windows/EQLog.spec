from pathlib import Path
from importlib.metadata import distribution
import sys

root = Path(SPECPATH).parent
pyinstaller_dist = distribution('pyinstaller')
bootloader_license = next(pyinstaller_dist.locate_file(p) for p in pyinstaller_dist.files
                          if p.name == 'COPYING.txt')
a = Analysis(
    [str(root / 'launch.pyw')],
    pathex=[str(root)],
    binaries=[],
    datas=[(str(root / 'LICENSE'), 'licenses'),
           (str(root / 'README.md'), 'documentation'),
           (str(Path(sys.base_prefix) / 'LICENSE.txt'), 'licenses/python'),
           (str(bootloader_license), 'licenses/pyinstaller'),
           (str(root / 'windows' / 'third-party' / 'Tcl-LICENSE.txt'), 'licenses/tcl')],
    hiddenimports=[],
    hookspath=[],
    runtime_hooks=[],
    excludes=['unittest', 'pip', 'setuptools'],
    noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz, a.scripts, [], exclude_binaries=True,
    name='EQLog', debug=False, bootloader_ignore_signals=False,
    strip=False, upx=False, console=False,
    icon=str(root / 'assets' / 'eqlog.ico'),
    version=str(root / 'build' / 'windows' / 'version-info.txt'),
)
coll = COLLECT(exe, a.binaries, a.datas, strip=False, upx=False, name='EQLog')
