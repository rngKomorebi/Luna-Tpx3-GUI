"""How tpx3dump is launched on this machine: natively, or through WSL.

Also the Windows -> WSL path translation and the WSL drive-mount checks.
Qt-free.
"""

from __future__ import annotations

import os
import re
import shlex
import subprocess
from dataclasses import dataclass
from pathlib import Path

from .common import _NO_WINDOW, IS_WINDOWS

LOG_LEVELS = ["", "off", "trace", "debug", "info", "warn", "error"]

def win_to_wsl(path: str) -> str:
    r"""C:\Users\bruce\x  ->  /mnt/c/Users/bruce/x"""
    p = str(path).replace("/", "\\")
    m = re.match(r"^([A-Za-z]):\\(.*)$", p)
    if not m:
        if p.startswith("\\\\"):
            raise ValueError(
                "UNC paths are not supported by the WSL backend:\n  " + str(path) +
                "\nMap it to a drive letter, or copy the data to a local disk.")
        return str(path).replace("\\", "/")
    drive, rest = m.group(1).lower(), m.group(2).replace("\\", "/")
    return "/mnt/" + drive + "/" + rest


def drive_letter(path) -> str:
    r"""Lower-case drive letter of a Windows path, or "" if it has none."""
    m = re.match(r"^([A-Za-z]):", str(path))
    return m.group(1).lower() if m else ""


def _wsl_text(out: bytes) -> str:
    for enc in ("utf-8", "utf-16-le"):
        try:
            return out.decode(enc).replace(chr(0), "")
        except UnicodeDecodeError:
            continue
    return ""


# Is /mnt/<letter> a real drive, or just an empty leftover directory? An
# unmounted drive can leave its mountpoint behind, so the presence of /mnt/e
# proves nothing -- ask whether something is mounted there, and fall back to
# "does it have any content" for distros without mountpoint(1).
_MOUNT_TEST = ('for d in "$@"; do mountpoint -q "/mnt/$d" 2>/dev/null || '
               '[ -n "$(ls -A "/mnt/$d" 2>/dev/null)" ] || printf "%s\\n" "$d"; done')

_PATH_TEST = 'for p in "$@"; do [ -e "$p" ] || printf "%s\\n" "$p"; done'


def _wsl_filter(script: str, items) -> list:
    """Run a little shell filter in WSL over items, return the ones it printed.

    On any failure to even reach WSL, report nothing missing: a preflight
    check that cannot run must not block a run that would have worked.
    """
    items = [str(i) for i in items]
    if not items:
        return []
    try:
        r = subprocess.run(["wsl.exe", "-e", "bash", "-c", script, "_"] + items,
                           capture_output=True, timeout=60,
                           creationflags=_NO_WINDOW)
    except Exception:
        return []
    return [ln.strip() for ln in _wsl_text(r.stdout).splitlines() if ln.strip()]


def wsl_unmounted_drives(letters) -> list:
    """Which of these drive letters are not mounted under /mnt inside WSL?

    WSL auto-mounts *fixed* disks only. A USB stick, card reader or other
    removable volume never appears there, so tpx3dump simply cannot see data
    stored on it -- it logs "Skipping file ... is not a directory" and then
    panics with "index out of bounds: the len is 0".
    """
    return sorted(_wsl_filter(_MOUNT_TEST, sorted(set(letters))))


def wsl_missing_paths(paths) -> list:
    """Which of these WSL paths does WSL not actually see?"""
    return _wsl_filter(_PATH_TEST, paths)


def wsl_mount_drive(letter: str):
    """Mount X: at /mnt/x inside WSL. -> (ok, error message).

    Runs as root via `wsl.exe -u root`, which needs no password. The mount
    lasts until WSL shuts down, so this may have to be repeated after a
    reboot or `wsl --shutdown`.
    """
    low = letter.lower()
    cmd = ("mkdir -p /mnt/{0}; mountpoint -q /mnt/{0} || "
           "mount -t drvfs {1}: /mnt/{0}").format(low, low.upper())
    try:
        r = subprocess.run(["wsl.exe", "-u", "root", "-e", "bash", "-c", cmd],
                           capture_output=True, timeout=60,
                           creationflags=_NO_WINDOW)
    except Exception as exc:
        return False, str(exc)
    if r.returncode == 0:
        return True, ""
    return False, (_wsl_text(r.stderr) + _wsl_text(r.stdout)).strip() or         "mount failed (exit %d)" % r.returncode

# ---------------------------------------------------------------------------
# backend: how do we actually launch tpx3dump on this machine
# ---------------------------------------------------------------------------

@dataclass
class Backend:
    kind: str = "none"        # "native" | "wsl" | "none"
    exe: str = ""             # executable path as the launcher will see it
    distro: str = ""          # WSL distro name, informational
    detail: str = ""          # human readable status line

    def translate(self, path) -> str:
        """Convert a local path into what the executable will see."""
        if self.kind == "wsl":
            return win_to_wsl(str(path))
        return str(path)

    def argv(self, args) -> list:
        """Full argv for Popen, given tpx3dump's own arguments."""
        if self.kind == "wsl":
            return ["wsl.exe", "-e", self.exe] + list(args)
        return [self.exe] + list(args)

    def display(self, args) -> str:
        return " ".join(shlex.quote(a) for a in self.argv(args))

    @property
    def usable(self) -> bool:
        return self.kind in ("native", "wsl")


def wsl_distros() -> list:
    """Installed WSL distributions, or [] if WSL has none / is absent."""
    try:
        out = subprocess.run(["wsl.exe", "-l", "-q"], capture_output=True,
                             timeout=20, creationflags=_NO_WINDOW).stdout
    except Exception:
        return []
    text = None
    for enc in ("utf-16-le", "utf-8"):
        try:
            text = out.decode(enc)
            break
        except UnicodeDecodeError:
            continue
    if text is None:
        return []
    text = text.replace("\x00", "")
    if "Usage: wsl.exe" in text or "--install" in text:
        return []                      # wsl.exe present but no distro installed
    return [ln.strip() for ln in text.splitlines() if ln.strip()]


def detect_backend(luna_dir: str) -> Backend:
    """Work out the best way to run tpx3dump from a Luna install directory."""
    if not luna_dir:
        return Backend(detail="No Luna directory set - browse to it above.")
    root = Path(luna_dir)
    if not root.is_dir():
        return Backend(detail="Not a directory: " + str(root))

    native_exe = linux_exe = None
    for d in (root / "bin", root):          # accept the root or bin/ itself
        if IS_WINDOWS and (d / "tpx3dump.exe").is_file():
            native_exe = d / "tpx3dump.exe"
        if (d / "tpx3dump").is_file():
            linux_exe = d / "tpx3dump"

    if native_exe:
        return Backend("native", str(native_exe),
                       detail="native Windows build: " + str(native_exe))

    if linux_exe and not IS_WINDOWS:
        if not os.access(linux_exe, os.X_OK):
            try:
                linux_exe.chmod(linux_exe.stat().st_mode | 0o111)
            except Exception:
                return Backend(detail=str(linux_exe) + " is not executable "
                               "(run: chmod +x '" + str(linux_exe) + "')")
        return Backend("native", str(linux_exe), detail="native: " + str(linux_exe))

    if linux_exe and IS_WINDOWS:
        distros = wsl_distros()
        if distros:
            lx = win_to_wsl(str(linux_exe))
            return Backend("wsl", lx, distro=distros[0],
                           detail="via WSL (" + distros[0] + "): " + lx)
        return Backend(detail="Found the Linux tpx3dump but no WSL distribution "
                              "is installed. Install one (wsl --install -d Ubuntu) "
                              "or use 'Export .sh' to run the queue on Ubuntu.")

    return Backend(detail="No tpx3dump or tpx3dump.exe found under " + str(root))
