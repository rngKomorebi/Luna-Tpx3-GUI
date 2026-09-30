"""Application identity and small helpers shared by every layer.

Qt-free: importing this never pulls in PySide6.
"""

from __future__ import annotations

import platform
import subprocess
from pathlib import Path

# The package directory. Data shipped with it (the icon) is found relative to
# this, which holds for a source checkout and a pip install alike.
PKG_DIR = Path(__file__).resolve().parent.parent
ICON_DIR = PKG_DIR / "icon"

APP_NAME = "Luna Tpx3 GUI"

IS_WINDOWS = platform.system() == "Windows"

# Base name of the .desktop file install-linux.sh writes (its $app_id). GNOME
# and other Wayland shells match a window to its launcher by this, and that is
# where they get the dock/switcher icon from -- see set_linux_desktop_name().
DESKTOP_FILE_NAME = "luna-tpx3-gui-qt"

# Windows wants the .ico: it carries 16/24/32/48/64/128/256 px renditions, so
# the title bar and taskbar get a real small icon instead of a downscaled
# 1024 px PNG. Everywhere else prefer the PNG -- .ico support on Linux depends
# on an optional Qt image plugin, and a missing plugin means no icon at all.
_ICON_CANDIDATES = ((ICON_DIR / "luna-tpx3-gui.ico",
                     ICON_DIR / "screen.png") if IS_WINDOWS else
                    (ICON_DIR / "screen.png",
                     ICON_DIR / "luna-tpx3-gui.ico"))
# Fall back silently if the icon folder is missing (a partial copy).
ICON_PATH = next((p for p in _ICON_CANDIDATES if p.is_file()), None)

# Windows shows the *interpreter's* icon in the taskbar unless the process
# declares an explicit AppUserModelID, which is why a python.exe-hosted Qt app
# gets the Python logo however carefully setWindowIcon() is called.
APP_USER_MODEL_ID = "cz.cvut.fjfi.luna-tpx3-gui"

_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0) if IS_WINDOWS else 0

def human_size(n: float) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024 or unit == "GB":
            return f"{n:.0f} {unit}" if unit == "B" else f"{n:.1f} {unit}"
        n /= 1024.0
    return f"{n:.1f} GB"
