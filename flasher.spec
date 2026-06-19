# PyInstaller spec for the FPVRaceOne Flasher.
#   Build:  pyinstaller flasher.spec
#   Output: dist/FPVRaceOne-Flasher.exe   (single portable file, no installer)
#
# esptool ships data files (stub flasher JSONs) and dynamically-imported target
# modules that PyInstaller's static analysis misses — collect them explicitly.

from PyInstaller.utils.hooks import collect_data_files, collect_submodules

datas = collect_data_files("esptool")
# Bundle the GUI image + icon so flasher.resources.asset_path() finds them
# under sys._MEIPASS/flasher/assets at runtime.
datas += [
    ("flasher/assets/product.png", "flasher/assets"),
    ("flasher/assets/icon.png", "flasher/assets"),
    ("flasher/assets/icon.ico", "flasher/assets"),
]
hiddenimports = (
    collect_submodules("esptool")
    + collect_submodules("serial")
)

a = Analysis(
    ["run.py"],
    pathex=[],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    runtime_hooks=[],
    excludes=["tkinter"],
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="FPVRaceOne-Flasher",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    runtime_tmpdir=None,
    console=False,          # GUI app — no console window
    disable_windowed_traceback=False,
    icon="flasher/assets/icon.ico",
)
