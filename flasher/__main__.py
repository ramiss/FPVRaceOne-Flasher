"""Entry point: `python -m flasher` (and the PyInstaller bundle's start point)."""

import sys

from .gui import main

if __name__ == "__main__":
    sys.exit(main())
