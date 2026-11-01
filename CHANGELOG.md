# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.2.0] - 01-11-2026

### Added

- Inspect HDF5 tab: double-click a dataset (or **View rows...**) to scroll
  through its rows in a window of their own. Only the rows on screen are read,
  so even a 300-million-row dataset opens instantly; jump to any row, first or
  last; column headers give type and unit; Ctrl+C copies the selection.
- Advanced tab: a control for every `tpx3dump process` option, including the
  ones that previously needed *extra arguments* (`--layout`, `--n-phases`,
  `--clustering-algorithm`, `--kuttruff-buffer-size`, `--discard-pixel-data`,
  the compression options, `--hdf5-chunk-size`, the timewalk options and
  `--ctot-cut`). Each has a one-line note on what it does and a tooltip with
  the details and `tpx3dump`'s default.
- Values `tpx3dump` would reject (a time without its unit, a non-number) are
  caught before Run, Preview or Export .sh.
- Help menu above the tabs (F1): a Help window explaining every tab, option
  and flag, plus name templates, the file's columns and units, TDC and
  troubleshooting, with a topic list and a Find box. The flag reference is
  generated from the same table as the Advanced tab, so the two cannot
  disagree. **All flags explained...** on the Advanced tab jumps straight to
  it.
- Path fields (Luna folder, output folder, HDF5 file, timewalk file) drop the
  quotes of a pasted *Copy as path* and accept a file or folder dragged in
  from Explorer; the Add folders paste box takes dragged folders too. A path
  pasted or dropped into **HDF5 file** opens straight away.

### Changed

- Process tab: the amber "Advanced: ..." line is now an **Advanced flags**
  button -- grey for a plain run, yellow with a count once anything deviates
  -- that lists every setting in effect, one per row.
- Process tab: **Add files...** and **Remove** are gone; **Clear all** is now
  **Clear**. The *Measurement folder* column is gone from **Files found**
  (hover a row for the full input and output paths).
- The Light/Dark buttons moved into a **View** menu, left of **Help**.
- On Windows the file dialogs are Explorer's own (Alt+D, paste into the
  address bar, Quick Access). They follow Windows' light/dark setting rather
  than the app's.
- The flags are defined once, in `functions/flags.py`, which drives the
  widgets, settings, summary line, reset and command line alike.

### Fixed

- README examples passed `--eps-t 100`; `tpx3dump` expects a unit, e.g.
  `200ns`.
- A code comment claimed that without `--tof-tdc-reference` tpx3dump uses a
  default edge; it computes no ToF at all.

## [0.1.0] - 30-09-2026

First public release.

Luna is not included: the GUI drives the user's own, unmodified `tpx3dump`.
There is deliberately no bundled executable on any platform, so the GUI cannot
be passed on with the Luna binaries packed inside; it runs from source on both
Linux and Windows.

### Added

- Process tab: queue `.tpx3` files or whole folders (searched recursively),
  run `tpx3dump process` over the batch, stream its output into the log.
- Backend detection: native `tpx3dump` on Linux, the Linux build through WSL
  on Windows, with Windows -> `/mnt/...` path translation and a pre-run check
  (and offer to mount) for drives WSL cannot see.
- Advanced tab: output placement (beside / flat / mirrored tree), name
  templates built from `measurement_metadata.json`, `tpx3dump` flags, command
  preview and `.sh` export.
- Inspect HDF5 tab: dataset summary, TDC edge statistics, six plots, and the
  TDC columns (`/PixelHitsTDC`, `/ClustersTDC`) written beside the originals.
- Qt-free Python API: `read_tdcs`, `add_tdc_columns`, `read_with_tdc`.
- Light and dark themes; plot styles from `komorebi_mpl` when installed.
- Linux menu launcher and Windows Desktop shortcut installers.
  `install-linux.sh` builds the private venv (from `requirements.txt`) and the
  Desktop icon by default; `--no-venv` and `--no-desktop-icon` opt out.
  `install-windows.ps1` likewise builds a venv from `requirements.txt`, at
  `%USERPROFILE%\venvs\luna-tpx3-gui` (`-VenvName` renames it, `-NoVenv`
  skips it), and `run_gui.bat` uses that venv too.
- Packaging: `pyproject.toml` with the `luna-tpx3-gui` console script and the
  `analysis` / `dev` extras; `python -m luna_tpx3_gui` also starts the app.
- pytest suite for the Qt-free core, ruff via pre-commit, and GitHub Actions
  for the tests (Ubuntu and Windows, Python 3.10-3.13) and the Sphinx docs.
- README: a prominent "Luna is not included" note with a who-does-what table,
  and worked examples (whole campaigns, many folders at once, Rescan during a
  live campaign, flat / mirrored output, batch-wide flags, selective
  overwrite, `.sh` export, TDC columns).
- Advanced tab: a Browse button for the output folder.

### Changed

- Code split from the single `luna_tpx3_gui_qt.py` into the
  `src/luna_tpx3_gui` package (`functions/` Qt-free core, `gui/` Qt app).
- Advanced tab re-laid out: it scrolls instead of squeezing its fields when
  the window is short, the flags sit in an aligned two-column grid, and the
  action buttons stay pinned below the options. The intro showing the default
  `tpx3dump` command is larger, with the command set off as a code block.
