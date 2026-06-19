"""Top-level launcher used both for `python run.py` (dev) and as the
PyInstaller entry script (see flasher.spec)."""

import sys

from flasher.gui import main

if __name__ == "__main__":
    sys.exit(main())
