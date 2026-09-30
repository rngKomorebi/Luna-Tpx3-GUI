#!/usr/bin/env bash
# Launch Luna Tpx3 GUI (Qt 6) on Linux.
#
# Picks an interpreter in this order:
#   $PYTHON  ->  .venv beside this script  ->  the venv install-linux.sh makes
#   ->  system python3
# and reports a missing PySide6 graphically, because when this is started from
# the desktop menu there is no terminal to print to.
set -euo pipefail

here="$(cd "$(dirname "$(readlink -f "${BASH_SOURCE[0]}")")" && pwd)"
data_dir="${XDG_DATA_HOME:-$HOME/.local/share}/luna-tpx3-gui-qt"

py=""
for cand in "${PYTHON:-}" "$here/.venv/bin/python" "$data_dir/venv/bin/python"; do
    if [ -n "$cand" ] && [ -x "$cand" ]; then py="$cand"; break; fi
done
[ -n "$py" ] || py="$(command -v python3 || true)"

die() {
    if command -v zenity >/dev/null 2>&1; then
        zenity --error --no-markup --width=520 --title="Luna Tpx3 GUI (Qt)" --text="$1"
    elif command -v kdialog >/dev/null 2>&1; then
        kdialog --error "$1"
    elif command -v xmessage >/dev/null 2>&1; then
        xmessage -center "$1"
    fi
    echo "$1" >&2
    exit 1
}

[ -n "$py" ] || die "No python3 found.

Install it with:
    sudo apt install python3 python3-venv"

"$py" -c 'import PySide6' >/dev/null 2>&1 || die "Python is present but PySide6 is not.

Install it with:
    $py -m pip install PySide6

or run ./install-linux.sh to build a private venv with everything."

# Qt 6.5+ needs libxcb-cursor0, and the failure message it prints on its own
# ('could not load the Qt platform plugin \"xcb\"') does not say which package
# is missing. Check up front so the user gets an actionable message instead.
if ! "$py" -c 'from PySide6.QtWidgets import QApplication' >/dev/null 2>&1; then
    die "PySide6 is installed but its Qt libraries will not load.

On Ubuntu this is almost always a missing system library:
    sudo apt install libxcb-cursor0 libxkbcommon-x11-0 libegl1

Run this in a terminal to see the real error:
    $py -c 'from PySide6.QtWidgets import QApplication'"
fi

exec "$py" "$here/src/main.py" "$@"
