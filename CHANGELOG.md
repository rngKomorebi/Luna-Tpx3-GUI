# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.1.0] - Unreleased

First public release. Put the date on this heading when it is tagged, and
start a fresh `## [Unreleased]` section above it.

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
  `install-linux.sh` builds the private venv and the Desktop icon by default.

### Changed

- Code split from the single `luna_tpx3_gui_qt.py` into the
  `src/luna_tpx3_gui` package (`functions/` Qt-free core, `gui/` Qt app).
- Advanced tab re-laid out: it scrolls instead of squeezing its fields when
  the window is short, the flags sit in an aligned two-column grid, and the
  action buttons stay pinned below the options.
