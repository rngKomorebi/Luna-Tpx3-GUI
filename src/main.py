"""Entry point for Luna Tpx3 GUI.

Run directly from the repository root, no install needed:
    python src/main.py

This is also what run_gui.sh, run_gui.bat and the shortcuts made by
install-linux.sh / install-windows.ps1 start.
"""

import os
import sys

# Ensure src/ is on sys.path so `luna_tpx3_gui` is importable when running
# straight from the repo, without a pip install.
try:
    _HERE = os.path.dirname(os.path.abspath(__file__))
except NameError:
    _HERE = os.path.abspath(os.getcwd())
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

from luna_tpx3_gui.main import main  # noqa: E402

if __name__ == "__main__":
    main()
