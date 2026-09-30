# Installation

Whichever way you install the GUI, you also need your own ASI Luna
installation (the Ubuntu build, containing `bin/tpx3dump`). Luna is not part
of this project and none of the options below provides it.

There is deliberately no standalone executable: a self-contained bundle makes
it too easy to pass the GUI on with the Luna binaries packed inside, which
would break Luna's licence. The GUI runs from source on both Linux and
Windows. On Windows, `tpx3dump` runs through WSL (see the README's *Windows*
section).

## From source

```bash
git clone https://github.com/rngKomorebi/Luna-Tpx3-GUI
cd Luna-Tpx3-GUI
python -m venv .venv
# Windows:  .venv\Scripts\activate
# Linux:    source .venv/bin/activate
pip install -e ".[analysis]"
luna-tpx3-gui
```

`pip install -e .` alone installs only PySide6, which is enough to build
and run batches; the `analysis` extra adds h5py, numpy, pandas, matplotlib
and komorebi_mpl for the Inspect tab, the TDC columns and the plots.

On Linux, `./install-linux.sh` sets up a private venv, a menu launcher and a
Desktop icon instead (`--no-venv` / `--no-desktop-icon` to skip either); on
Windows, `.\install-windows.ps1` creates a Desktop shortcut. Both are
described in the README.
