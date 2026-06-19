"""Resolve bundled asset paths in both dev runs and the PyInstaller one-file exe.

PyInstaller unpacks bundled data to a temp dir exposed as `sys._MEIPASS`; in a
normal `python run.py` run the assets sit next to this module.
"""

import sys
from pathlib import Path


def asset_path(name: str) -> Path:
    base = getattr(sys, "_MEIPASS", None)
    if base:
        return Path(base) / "flasher" / "assets" / name
    return Path(__file__).resolve().parent / "assets" / name
