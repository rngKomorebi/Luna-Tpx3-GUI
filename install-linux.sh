#!/usr/bin/env bash
# Make Luna Tpx3 GUI (Qt 6) launchable with one click on Ubuntu.
#
# Installs a .desktop entry (and its icon) into the current user's
# ~/.local/share, so the GUI shows up in the Activities menu and can be pinned
# to the dock. No root needed, nothing outside $HOME is touched.
#
# This installs *this GUI only*. It never copies, moves or repackages the Luna
# binaries -- you point the GUI at your own Luna installation at runtime.
#
#   ./install-linux.sh                    the full install: a private venv with
#                                         everything in requirements.txt, the
#                                         menu launcher, and a Desktop icon
#   ./install-linux.sh --no-venv          skip the venv; use the system python3
#                                         (PySide6 must already be installed)
#   ./install-linux.sh --no-desktop-icon  skip the icon on the Desktop
#   ./install-linux.sh --uninstall        remove everything this script installed
#
# --with-venv and --desktop-icon are still accepted; both are now the default.
set -euo pipefail

here="$(cd "$(dirname "$(readlink -f "${BASH_SOURCE[0]}")")" && pwd)"
app_id="luna-tpx3-gui-qt"
legacy_app_id="tpx3dump-gui-qt"
data_home="${XDG_DATA_HOME:-$HOME/.local/share}"
apps_dir="$data_home/applications"
icon_dir="$data_home/icons/hicolor/scalable/apps"
png_icon_dir="$data_home/icons/hicolor/1024x1024/apps"
venv_dir="$data_home/$app_id/venv"
desktop_file="$apps_dir/$app_id.desktop"

want_venv=1
want_desktop_icon=1
do_uninstall=0
for arg in "$@"; do
    case "$arg" in
        --with-venv)        want_venv=1 ;;
        --no-venv)          want_venv=0 ;;
        --desktop-icon)     want_desktop_icon=1 ;;
        --no-desktop-icon)  want_desktop_icon=0 ;;
        --uninstall)        do_uninstall=1 ;;
        -h|--help)          sed -n '2,19p' "$0"; exit 0 ;;
        *) echo "Unknown option: $arg (try --help)" >&2; exit 2 ;;
    esac
done

say() { printf '  %s\n' "$*"; }

# Honour a localised Desktop folder (~/Escritorio, ~/Bureau, ...) so that
# install and uninstall always agree on where the shortcut went.
desktop_dir() { xdg-user-dir DESKTOP 2>/dev/null || echo "$HOME/Desktop"; }

refresh_menus() {
    command -v update-desktop-database >/dev/null 2>&1 \
        && update-desktop-database "$apps_dir" 2>/dev/null || true
    command -v gtk-update-icon-cache >/dev/null 2>&1 \
        && gtk-update-icon-cache -f -t "$data_home/icons/hicolor" 2>/dev/null || true
}

# ---------------------------------------------------------------- uninstall
if [ "$do_uninstall" = 1 ]; then
    echo "Removing the Luna Tpx3 GUI (Qt) launcher..."
    for f in "$desktop_file" "$icon_dir/$app_id.svg" "$png_icon_dir/$app_id.png" "$(desktop_dir)/$app_id.desktop" \
             "$apps_dir/$legacy_app_id.desktop" "$icon_dir/$legacy_app_id.svg" \
             "$png_icon_dir/$legacy_app_id.png" "$(desktop_dir)/$legacy_app_id.desktop"; do
        [ -e "$f" ] && rm -f "$f" && say "removed $f"
    done
    if [ -d "$venv_dir" ]; then
        say "the private venv is still at $venv_dir"
        say "delete it yourself if you want the space back:  rm -rf '$venv_dir'"
    fi
    refresh_menus
    echo "Done. The GUI's own files in $here were left alone."
    exit 0
fi

# ------------------------------------------------------------------- checks
who_am_i="${USER:-$(id -un 2>/dev/null || echo "$(basename "$HOME")")}"
echo "Installing the Luna Tpx3 GUI (Qt) launcher for $who_am_i"
say "source     : $here"
say "launcher   : $desktop_file"

for required in "$here/src/main.py" "$here/run_gui.sh" "$here/requirements.txt"; do
    [ -f "$required" ] || { echo "Missing $required -- run this from inside the qt6 folder." >&2; exit 1; }
done
chmod +x "$here/run_gui.sh"

if ! command -v python3 >/dev/null 2>&1; then
    echo "python3 is not installed. Run:  sudo apt install python3 python3-venv" >&2
    exit 1
fi

if [ "$want_venv" = 0 ] && ! python3 -c 'import PySide6' >/dev/null 2>&1; then
    echo
    echo "WARNING: PySide6 is missing, so the GUI cannot start yet."
    echo "         Fix it with:  python3 -m pip install PySide6"
    echo "         ...or re-run this script without --no-venv."
    echo "         Continuing with the launcher install anyway."
    echo
fi

# --------------------------------------------------------- venv (default)
if [ "$want_venv" = 1 ]; then
    echo "Building a private venv (PySide6 + the Inspect tab stack)..."
    say "(skip with --no-venv if PySide6 is already installed system-wide)"
    if ! python3 -c 'import venv' >/dev/null 2>&1; then
        echo "python3-venv is missing. Run:  sudo apt install python3-venv" >&2
        echo "...or re-run with --no-venv to use the system python3." >&2
        exit 1
    fi
    python3 -m venv "$venv_dir"
    "$venv_dir/bin/python" -m pip install --quiet --upgrade pip
    "$venv_dir/bin/python" -m pip install --quiet -r "$here/requirements.txt"
    say "venv ready at $venv_dir (~450 MB); run_gui.sh will pick it up automatically"
fi

# Qt 6.5+ will not start without libxcb-cursor0, and its own error message does
# not name the package. Warn while we still have the user's attention.
if ! dpkg -s libxcb-cursor0 >/dev/null 2>&1; then
    say "NOTE: libxcb-cursor0 is not installed; Qt 6 needs it to open a window."
    say "      sudo apt install libxcb-cursor0"
fi

# --------------------------------------------------------------- icon + entry
mkdir -p "$apps_dir" "$png_icon_dir"

icon_src=""
for cand in "$here/src/luna_tpx3_gui/icon/screen.png"; do
    [ -f "$cand" ] && { icon_src="$cand"; break; }
done

if [ -n "$icon_src" ]; then
    install -m 644 "$icon_src" "$png_icon_dir/$app_id.png"
    icon_ref="$png_icon_dir/$app_id.png"
    say "icon       : $icon_ref"
else
    icon_ref="utilities-terminal"        # harmless stock fallback
    say "icon       : no icon found, using a stock icon"
fi

cat > "$desktop_file" <<EOF
[Desktop Entry]
Type=Application
Version=1.0
Name=Luna Tpx3 GUI (Qt)
GenericName=Timepix3 batch converter
Comment=Batch-convert Timepix3 .tpx3 files to HDF5 using ASI Luna
Exec="$here/run_gui.sh"
Icon=$icon_ref
Path=$here
Terminal=false
StartupNotify=true
StartupWMClass=$app_id
Categories=Science;Physics;DataVisualization;Utility;
Keywords=timepix;tpx3;tpx3dump;luna;hdf5;asi;detector;qt;
EOF
chmod 644 "$desktop_file"

if command -v desktop-file-validate >/dev/null 2>&1; then
    if desktop-file-validate "$desktop_file"; then
        say "desktop entry validated"
    else
        say "desktop-file-validate FAILED -- the menu will ignore this entry:"
        sed 's/^/      /' "$desktop_file" >&2
    fi
else
    say "desktop-file-validate not found; cannot check the entry is well-formed"
    say "      sudo apt install desktop-file-utils"
fi

# Prove the file really landed, so a silent write failure cannot be mistaken
# for the menu simply needing a refresh.
if [ -s "$desktop_file" ]; then
    say "wrote      : $desktop_file"
else
    echo "ERROR: $desktop_file was not written." >&2
    exit 1
fi

# ---------------------------------------------------- desktop icon (default)
if [ "$want_desktop_icon" = 1 ]; then
    desk="$(desktop_dir)"
    if [ -d "$desk" ]; then
        install -m 755 "$desktop_file" "$desk/$app_id.desktop"
        # GNOME will not launch an untrusted .desktop until it is marked so.
        command -v gio >/dev/null 2>&1 \
            && gio set "$desk/$app_id.desktop" metadata::trusted true 2>/dev/null || true
        say "desktop icon: $desk/$app_id.desktop"
        say "if GNOME shows it as untrusted, right-click it once and choose 'Allow Launching'"
    else
        say "no Desktop folder found, skipped the desktop icon"
    fi
fi

refresh_menus

cat <<EOF

Done.

  Launch it from the Activities menu -- search for "Luna" -- or run
  "$here/run_gui.sh"

  First time in the GUI: Advanced tab, browse to your Luna folder (the one
  containing bin/tpx3dump), then click "Check install".

  To remove the launcher again:  ./install-linux.sh --uninstall
EOF
