"""The main window: Process, Advanced and Inspect HDF5 tabs."""

from __future__ import annotations

import os
import shlex
import subprocess
import time
import traceback
from pathlib import Path

from PySide6.QtCore import QProcess, Qt, QTimer
from PySide6.QtGui import QFontDatabase, QIcon
from PySide6.QtWidgets import (
    QAbstractItemView, QApplication, QCheckBox, QComboBox, QDialog,
    QDialogButtonBox, QFileDialog, QFrame, QGridLayout, QGroupBox,
    QHBoxLayout, QHeaderView, QLabel, QLineEdit, QListWidget, QMainWindow,
    QMessageBox, QPlainTextEdit, QProgressBar, QRadioButton, QScrollArea,
    QSplitter, QTableWidget, QTableWidgetItem, QTabWidget, QVBoxLayout,
    QWidget)

from ..functions.backend import (LOG_LEVELS, Backend, detect_backend,
                                 drive_letter, win_to_wsl, wsl_missing_paths,
                                 wsl_mount_drive, wsl_unmounted_drives)
from ..functions.common import (_NO_WINDOW, APP_NAME, ICON_PATH, IS_WINDOWS,
                                human_size)
from ..functions.config import load_config, save_config
from ..functions.naming import (DEFAULT_TEMPLATE, PRESET_TEMPLATES,
                                TEMPLATE_HELP, Job, measurement_context,
                                migrate_template, render_name)
from ..functions.plotting import (CSIZE_BINS, CSIZE_MAX, PLOT_FIGSIZE,
                                  PLOT_TITLES, STOT_TARGET_BINS, TOT_LSB_NS,
                                  plot_style_context)
from ..functions.tdc import (TDC_DATASET, TDC_REFERENCES,
                             TDC_SECONDS_PER_TICK, TDC_SOURCES, TDC_STAMP,
                             TOF_TDC_REFERENCES, add_tdc_columns,
                             describe_tdc_types, read_tdc_events, read_tdcs,
                             read_with_tdc, tag_times_with_tdc,
                             tdc_reference_edges)
from .models import FolderModel, JobModel
from .style import (_FONT_MONO_CANDIDATES, _FONT_SANS_CANDIDATES, PALETTES,
                    build_palette, build_qss, pick_font)
from .widgets import CheckHeader, button, row, table, vline

# ---------------------------------------------------------------------------
# optional scientific stack (Inspect tab only)
# ---------------------------------------------------------------------------

def require_h5py(parent=None):
    try:
        import h5py
        import numpy
        return h5py, numpy
    except Exception:
        QMessageBox.critical(
            parent, APP_NAME,
            "This panel needs h5py and numpy.\n\n"
            "Install them into the interpreter running this GUI:\n"
            "    python -m pip install h5py numpy")
        return None, None


def require_pandas(parent=None):
    try:
        import pandas
        return pandas
    except Exception:
        QMessageBox.critical(
            parent, APP_NAME,
            "This panel needs pandas.\n\n"
            "Install it into the interpreter running this GUI:\n"
            "    python -m pip install pandas")
        return None

# ---------------------------------------------------------------------------
# main window
# ---------------------------------------------------------------------------

class MainWindow(QMainWindow):

    def __init__(self):
        super().__init__()
        self.cfg = load_config()
        self._template_migrated = migrate_template(self.cfg)
        self.jobs = []
        self.folders = []
        self.backend = Backend()
        self.proc = None
        self.todo = []
        self.stopping = False
        self.total = self.done = self.ok = self.failed = 0
        self.t_all = self.t_job = 0.0
        self.cur = -1

        self.theme_name = self.cfg.get("theme") if self.cfg.get("theme") in PALETTES else "light"
        self.pal = PALETTES[self.theme_name]
        self.sans = pick_font(_FONT_SANS_CANDIDATES, "Segoe UI" if IS_WINDOWS else "Sans")
        self.mono = pick_font(_FONT_MONO_CANDIDATES, "Consolas" if IS_WINDOWS else "Monospace")

        self.setWindowTitle(APP_NAME)
        # The layout's own minimum is 841x746 and its preferred hint 841x780,
        # but 841 wide cramps the six-column Files found table, so open a bit
        # wider than strictly needed and let the user shrink from there.
        # Whatever is asked for must never exceed the desktop it opens on: a
        # 1080p panel at 125% scaling leaves only 1536x832 of usable logical
        # space. _fit_to_screen() does the exact correction below, once the
        # frame size is knowable.
        avail = (self.screen() or QApplication.primaryScreen()).availableGeometry()
        self.resize(min(1080, avail.width()), min(760, avail.height()))
        self.setMinimumSize(min(840, avail.width()), min(620, avail.height()))
        self._fitted = False
        if ICON_PATH:
            self.setWindowIcon(QIcon(str(ICON_PATH)))

        self.job_model = JobModel(self)
        self.folder_model = FolderModel(self)

        central = QWidget()
        self.setCentralWidget(central)
        outer = QVBoxLayout(central)
        outer.setContentsMargins(12, 10, 12, 12)
        outer.setSpacing(8)

        # header: title + theme toggle
        title = QLabel(APP_NAME)
        title.setProperty("heading", True)
        self.b_light = button("Light", lambda: self.apply_theme("light"), toggle=True)
        self.b_dark = button("Dark", lambda: self.apply_theme("dark"), toggle=True)
        outer.addWidget(row(title, None, self.b_light, self.b_dark, spacing=4))

        self.tabs = QTabWidget()
        outer.addWidget(self.tabs, 1)
        self.tab_process = QWidget()
        self.tab_advanced = QWidget()
        self.tab_inspect = QWidget()
        self.tabs.addTab(self.tab_process, "Process")
        self.tabs.addTab(self.tab_advanced, "Advanced")
        self.tabs.addTab(self.tab_inspect, "Inspect HDF5")

        # Advanced first: it owns every option widget the others read.
        self._build_advanced(self.tab_advanced)
        self._build_process(self.tab_process)
        self._build_inspect(self.tab_inspect)
        self._connect_option_signals()

        self.apply_theme(self.theme_name)
        self.refresh_backend()
        self.update_adv_summary()

        # Restore last session's batch; deferred so the window paints first
        # even when the folders live on a slow or absent disk.
        saved = self.cfg.get("folders") or []
        self.folders = [{"path": f.get("path", ""),
                         "recursive": bool(f.get("recursive", True)),
                         "count": None}
                        for f in saved if isinstance(f, dict) and f.get("path")]
        if self.folders:
            self.folder_model.reset()
            QTimer.singleShot(300, self.scan_folders)

    # -- theme ------------------------------------------------------------

    def apply_theme(self, name):
        self.theme_name = name if name in PALETTES else "light"
        self.pal = PALETTES[self.theme_name]
        self.cfg["theme"] = self.theme_name
        app = QApplication.instance()
        app.setPalette(build_palette(self.pal))
        app.setStyleSheet(build_qss(self.pal, self.sans, self.mono))
        self.b_light.setChecked(self.theme_name == "light")
        self.b_dark.setChecked(self.theme_name == "dark")
        # Repaint model-driven colours (status text) under the new palette,
        # including the hand-drawn checkbox in the queue header.
        if getattr(self, "jhead", None):
            self.jhead.set_palette(self.pal)
        self.job_model.reset()
        self.sync_overwrite_header()
        self.folder_model.reset()
        self.refresh_backend()
        self.update_adv_summary()

    # -- process tab ------------------------------------------------------

    def _build_process(self, tab):
        """The main window: pick input, press Run. Nothing else.

        On its own this tab is exactly
            tpx3dump process -i NAME.tpx3 -o NAME.hdf5
        for every queued file. Anything that changes that lives on Advanced.
        """
        lay = QVBoxLayout(tab)
        lay.setContentsMargins(10, 12, 10, 10)
        lay.setSpacing(8)

        self.lbl_status = QLabel("")
        self.b_setup = button("Set up Luna...", self.goto_advanced)
        lay.addWidget(row(self.lbl_status, None, self.b_setup))

        # Non-default settings are invisible from here otherwise, and silently
        # renamed or relocated output is the surprise worth never having.
        self.lbl_adv = QLabel("")
        self.lbl_adv.setProperty("role", "warn")
        self.lbl_adv.setWordWrap(True)
        lay.addWidget(self.lbl_adv)

        # Additive actions on the left, destructive ones pushed to the far
        # right so "Clear all" can never be hit while reaching for "Add".
        cap_in = QLabel("Input")
        cap_in.setProperty("muted", True)
        lay.addWidget(row(
            cap_in,
            button("Add files...", self.add_files,
                   tip="Queue individual .tpx3 files"),
            button("Add folders...", self.add_folders_dialog,
                   tip="Queue every .tpx3 found under one or more folders"),
            vline(),
            button("Rescan", self.scan_folders,
                   tip="Re-read the batch folders and queue anything new"),
            None,
            button("Remove", self.remove_any, danger=True,
                   tip="Remove the selected folder(s) or file(s) from the queue"),
            button("Clear all", self.clear_queue, danger=True,
                   tip="Empty the queue and the folder list"),
        ))

        self.b_run = button("Run queue", self.run_queue, accent=True)
        self.b_stop = button("Stop", self.stop_run)
        self.b_stop.setEnabled(False)
        self.lbl_prog = QLabel("")
        self.pb = QProgressBar()
        self.pb.setFixedWidth(240)
        self.pb.setValue(0)
        self.pb.setTextVisible(False)      # only meaningful during a run
        self.pb.setVisible(False)          # and an empty bar is just noise
        # Run controls only. "Clear log" used to sit here despite having
        # nothing to do with running; it now lives on the log's own header.
        lay.addWidget(row(self.b_run, self.b_stop, None, self.lbl_prog, self.pb))

        split = QSplitter(Qt.Orientation.Horizontal)
        left = QWidget()
        llay = QVBoxLayout(left)
        llay.setContentsMargins(0, 0, 0, 0)
        llay.setSpacing(4)
        cap_l = QLabel("Folders to process")
        cap_l.setProperty("muted", True)
        llay.addWidget(cap_l)
        self.ftable = table(self.folder_model, stretch_cols=(0,), widths=(230, 56, 72))
        llay.addWidget(self.ftable, 1)

        right = QWidget()
        rlay = QVBoxLayout(right)
        rlay.setContentsMargins(0, 0, 0, 0)
        rlay.setSpacing(4)
        cap_r = QLabel("Files found")
        cap_r.setProperty("muted", True)
        rlay.addWidget(cap_r)
        self.jtable = table(self.job_model, stretch_cols=(3, 5),
                            widths=(110, 175, 70, 320, 108, 165))
        self.jhead = CheckHeader(JobModel.OVER, self.pal,
                                 JobModel.HEADERS[JobModel.OVER], self.jtable)
        self.jtable.setHorizontalHeader(self.jhead)
        self.jhead.setDefaultAlignment(Qt.AlignmentFlag.AlignLeft
                                       | Qt.AlignmentFlag.AlignVCenter)
        self.jhead.setHighlightSections(False)
        for i in range(self.job_model.columnCount()):
            self.jhead.setSectionResizeMode(
                i, QHeaderView.ResizeMode.Stretch if i in (3, 5)
                else QHeaderView.ResizeMode.Interactive)
        for i, w in enumerate((110, 175, 70, 320, 108, 165)):
            self.jtable.setColumnWidth(i, w)
        self.jhead.setSectionsClickable(True)   # setHorizontalHeader can reset it
        self.jhead.box_clicked.connect(self.toggle_all_overwrite)
        self.jtable.doubleClicked.connect(self._job_double_clicked)
        rlay.addWidget(self.jtable, 1)

        split.addWidget(left)
        split.addWidget(right)
        split.setStretchFactor(0, 1)
        split.setStretchFactor(1, 3)
        lay.addWidget(split, 3)

        cap_log = QLabel("Log")
        cap_log.setProperty("muted", True)
        lay.addWidget(row(cap_log, None,
                          button("Clear log", lambda: self.log_view.clear())))

        self.log_view = QPlainTextEdit()
        self.log_view.setReadOnly(True)
        self.log_view.setMaximumBlockCount(20000)   # long batches stay responsive
        self.log_view.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        lay.addWidget(self.log_view, 2)

    # -- advanced tab -----------------------------------------------------

    def _build_advanced(self, tab):
        """Everything that is not "-i FILE.tpx3 -o FILE.hdf5"."""
        # Scrolls rather than squeezes. Four groups of options are taller than
        # a laptop screen at 125% scaling leaves room for, and the window's
        # explicit minimum size lets it go shorter than this layout's own
        # minimum -- without a scroll area Qt then crushes the line edits and
        # combos below their height and they paint over one another.
        outer = QVBoxLayout(tab)
        outer.setContentsMargins(0, 0, 0, 0)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.viewport().setAutoFillBackground(False)   # the tab pane shows
        outer.addWidget(scroll)
        body = QWidget()
        scroll.setWidget(body)

        lay = QVBoxLayout(body)
        lay.setContentsMargins(12, 12, 12, 12)
        lay.setSpacing(12)

        # The one thing worth knowing before touching anything below, so it
        # reads first: larger text, and the command as a code block.
        intro = QVBoxLayout()
        intro.setSpacing(6)
        head = QLabel("All optional. Left alone, the Process tab runs exactly")
        head.setProperty("intro", True)
        cmd = QLabel("tpx3dump process -i NAME.tpx3 -o NAME.hdf5")
        cmd.setProperty("code", True)
        cmd.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        tail = QLabel("for every queued file, writing the .hdf5 beside its .tpx3.")
        tail.setProperty("intro", True)
        intro.addWidget(head)
        intro.addWidget(row(cmd, None, margins=(14, 0, 0, 0)))
        intro.addWidget(tail)
        lay.addLayout(intro)

        # Luna install ----------------------------------------------------
        g_luna = QGroupBox("Luna installation")
        gl = QGridLayout(g_luna)
        gl.setHorizontalSpacing(8)
        gl.setVerticalSpacing(8)
        gl.setColumnStretch(1, 1)
        gl.addWidget(QLabel("Folder:"), 0, 0)
        self.e_luna = QLineEdit(self.cfg.get("luna_dir", ""))
        self.e_luna.setPlaceholderText("the folder containing bin/tpx3dump")
        self.e_luna.editingFinished.connect(self.refresh_backend)
        gl.addWidget(self.e_luna, 0, 1)
        gl.addWidget(button("Browse...", self.pick_luna), 0, 2)
        gl.addWidget(button("Check install", self.check_install), 0, 3)
        self.lbl_backend = QLabel("")
        self.lbl_backend.setWordWrap(True)
        gl.addWidget(self.lbl_backend, 1, 0, 1, 4)
        lay.addWidget(g_luna)

        # Output ----------------------------------------------------------
        g_out = QGroupBox("Output")
        go = QGridLayout(g_out)
        go.setHorizontalSpacing(8)
        go.setVerticalSpacing(8)
        go.setColumnStretch(1, 1)
        self.rb_beside = QRadioButton("Next to the input file")
        self.rb_flat = QRadioButton("Output folder (flat)")
        self.rb_mirror = QRadioButton("Output folder (mirror tree)")
        mode = self.cfg.get("out_mode", "beside")
        {"beside": self.rb_beside, "flat": self.rb_flat,
         "mirror": self.rb_mirror}.get(mode, self.rb_beside).setChecked(True)
        for rb in (self.rb_beside, self.rb_flat, self.rb_mirror):
            rb.toggled.connect(lambda _c: self.recompute_outputs())
        go.addWidget(row(self.rb_beside, self.rb_flat, self.rb_mirror, None,
                         spacing=18), 0, 0, 1, 3)

        go.addWidget(QLabel("Output folder:"), 1, 0)
        self.e_outdir = QLineEdit(self.cfg.get("out_dir", ""))
        self.e_outdir.setPlaceholderText("used by the two 'Output folder' modes")
        self.e_outdir.textChanged.connect(lambda _t: self.recompute_outputs())
        go.addWidget(self.e_outdir, 1, 1)
        self.b_outdir = button("Browse...", self.pick_outdir)
        go.addWidget(self.b_outdir, 1, 2)

        go.addWidget(QLabel("Name template:"), 2, 0)
        self.e_template = QLineEdit(self.cfg.get("template", DEFAULT_TEMPLATE))
        self.e_template.textChanged.connect(lambda _t: self.recompute_outputs())
        go.addWidget(self.e_template, 2, 1)
        go.addWidget(button("Presets...", self.template_presets), 2, 2)

        # Two fixed lines on purpose. One unwrapped line of 20 placeholders is
        # a ~1070 px minimum width that pins the whole window wide, and a
        # word-wrapped QLabel is height-for-width, which a grid inside a group
        # box sizes unreliably -- it came out a line short and the rows below
        # ran into it.
        words = TEMPLATE_HELP.split()
        half = (len(words) + 1) // 2
        ph = QLabel("placeholders:  " + " ".join(words[:half]) + "\n"
                    + " " * 16 + " ".join(words[half:]))
        ph.setProperty("faint", True)
        ph.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        go.addWidget(ph, 3, 1, 1, 2)

        self.cb_skip = QCheckBox("Skip files whose output already exists")
        self.cb_skip.setChecked(bool(self.cfg.get("skip_existing", True)))
        skip_hint = QLabel("untick to overwrite them all -- or tick "
                           "'Overwrite' on single rows of the queue")
        skip_hint.setProperty("faint", True)
        go.addWidget(row(self.cb_skip, skip_hint, None, spacing=10),
                     4, 0, 1, 3)
        lay.addWidget(g_out)

        # Flags -------------------------------------------------------------
        # A label/field grid, two flags per row, so every field keeps its full
        # height and the labels line up instead of running into each other.
        g_opt = QGroupBox("tpx3dump flags  (blank = tpx3dump's own default)")
        gf = QGridLayout(g_opt)
        gf.setHorizontalSpacing(8)
        gf.setVerticalSpacing(8)
        gf.setColumnMinimumWidth(2, 24)       # gutter between the two pairs
        gf.setColumnStretch(5, 1)
        right = Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter

        def field(r, c, label, key, width=120):
            gf.addWidget(QLabel(label), r, c, right)
            e = QLineEdit(str(self.cfg.get(key, "")))
            e.setPlaceholderText("default")
            e.setFixedWidth(width)
            gf.addWidget(e, r, c + 1)
            return e

        self.e_eps_s = field(0, 0, "--eps-s", "eps_s")
        self.e_eps_t = field(0, 3, "--eps-t", "eps_t")
        self.e_ntb = field(1, 0, "--num-time-bins", "num_time_bins")
        self.e_tbi = field(1, 3, "--time-bin-interval", "time_bin_interval")

        gf.addWidget(QLabel("--log-level"), 2, 0, right)
        self.c_log = QComboBox()
        self.c_log.addItems(LOG_LEVELS)
        self.c_log.setCurrentText(self.cfg.get("log_level", ""))
        self.c_log.setFixedWidth(120)
        gf.addWidget(self.c_log, 2, 1)

        self.cb_raw = QCheckBox("--raw-only")
        self.cb_raw.setChecked(bool(self.cfg.get("raw_only", False)))
        self.cb_noclust = QCheckBox("--disable-clustering")
        self.cb_noclust.setChecked(bool(self.cfg.get("disable_clustering", False)))
        # The flag takes a value, so the checkbox -- not a blank combo entry --
        # is what decides whether it is passed at all. That way an unchecked
        # flag still remembers which reference was last picked.
        self.cb_tof = QCheckBox("--tof-tdc-reference")
        self.cb_tof.setChecked(bool(self.cfg.get("tof_tdc_reference_on", False)))
        self.c_tof = QComboBox()
        self.c_tof.addItems(TOF_TDC_REFERENCES)
        self.c_tof.setCurrentText(self.cfg.get("tof_tdc_reference",
                                               TOF_TDC_REFERENCES[0]))
        self.c_tof.setMinimumWidth(130)
        self.c_tof.setEnabled(self.cb_tof.isChecked())
        self.cb_tof.toggled.connect(self.c_tof.setEnabled)
        gf.addWidget(row(self.cb_raw, self.cb_noclust, vline(),
                         self.cb_tof, self.c_tof, None, spacing=14),
                     3, 0, 1, 6)

        gf.addWidget(QLabel("extra arguments:"), 4, 0, right)
        self.e_extra = QLineEdit(self.cfg.get("extra", ""))
        gf.addWidget(self.e_extra, 4, 1, 1, 5)
        hint = QLabel("Anything not listed above goes here verbatim -- "
                      "'Check install' prints the authoritative flag list.")
        hint.setProperty("faint", True)
        gf.addWidget(hint, 5, 1, 1, 5)
        lay.addWidget(g_opt)

        # After processing ---------------------------------------------------
        # Not a tpx3dump flag: the GUI reopens the finished .hdf5 and writes
        # the TDC columns into it itself. Kept visually apart from the flags
        # above so it is never mistaken for one.
        g_post = QGroupBox("After processing  (this GUI, not tpx3dump)")
        gp = QHBoxLayout(g_post)
        gp.setSpacing(8)
        self.cb_tdc = QCheckBox("Add TDC columns to each output .hdf5")
        self.cb_tdc.setChecked(bool(self.cfg.get("tdc_columns", False)))
        self.cb_tdc.setToolTip(
            "Tag every pixel hit and cluster with the TDC edge it follows, and "
            "write the result into the output file as /PixelHitsTDC and "
            "/ClustersTDC. The datasets tpx3dump wrote are left untouched.")
        gp.addWidget(self.cb_tdc)
        gp.addSpacing(10)
        gp.addWidget(QLabel("reference:"))
        self.c_tdcref = QComboBox()
        self.c_tdcref.addItems(TDC_REFERENCES)
        self.c_tdcref.setCurrentText(self.cfg.get("tdc_reference",
                                                  TDC_REFERENCES[0]))
        self.c_tdcref.setMinimumWidth(130)
        self.c_tdcref.setEnabled(self.cb_tdc.isChecked())
        self.cb_tdc.toggled.connect(self.c_tdcref.setEnabled)
        gp.addWidget(self.c_tdcref)
        gp.addStretch(1)
        lay.addWidget(g_post)
        lay.addStretch(1)

        # Outside the scroll area, so the actions stay in reach however far
        # the options above have been scrolled.
        outer.addWidget(row(
            button("Preview commands", self.preview),
            button("Export .sh", self.export_sh),
            button("Reset to defaults", self.reset_advanced),
            None,
            button("Back to Process", lambda: self.tabs.setCurrentWidget(self.tab_process)),
            margins=(12, 6, 12, 10)))

    def _connect_option_signals(self):
        for w in (self.e_template, self.e_eps_s, self.e_eps_t, self.e_ntb,
                  self.e_tbi, self.e_extra):
            w.textChanged.connect(self.update_adv_summary)
        self.c_log.currentTextChanged.connect(self.update_adv_summary)
        self.c_tof.currentTextChanged.connect(self.update_adv_summary)
        self.c_tdcref.currentTextChanged.connect(self.update_adv_summary)
        for w in (self.cb_skip, self.cb_raw, self.cb_noclust, self.cb_tof,
                  self.cb_tdc, self.rb_beside, self.rb_flat, self.rb_mirror):
            w.toggled.connect(self.update_adv_summary)
        # One TDC reference, two places to set it. setCurrentText is a no-op
        # when the text already matches, so Qt emits nothing back and the pair
        # settles instead of ping-ponging.
        self.c_tdcref.currentTextChanged.connect(self.c_tdcref_i.setCurrentText)
        self.c_tdcref_i.currentTextChanged.connect(self.c_tdcref.setCurrentText)

    # -- option accessors --------------------------------------------------

    def out_mode(self):
        if self.rb_flat.isChecked():
            return "flat"
        if self.rb_mirror.isChecked():
            return "mirror"
        return "beside"

    def goto_advanced(self):
        self.tabs.setCurrentWidget(self.tab_advanced)

    def advanced_summary(self):
        """Short description of everything that deviates from the plain run."""
        bits = []
        mode = self.out_mode()
        if mode == "flat":
            bits.append("output into one folder")
        elif mode == "mirror":
            bits.append("output into a mirrored tree")
        tmpl = self.e_template.text().strip()
        if tmpl and tmpl != DEFAULT_TEMPLATE:
            bits.append("renaming to " + tmpl)
        if not self.cb_skip.isChecked():
            bits.append("OVERWRITING existing output")
        for flag, w in (("--eps-s", self.e_eps_s), ("--eps-t", self.e_eps_t),
                        ("--num-time-bins", self.e_ntb),
                        ("--time-bin-interval", self.e_tbi)):
            val = w.text().strip()
            if val:
                bits.append(flag + " " + val)
        if self.c_log.currentText().strip():
            bits.append("--log-level " + self.c_log.currentText().strip())
        if self.cb_raw.isChecked():
            bits.append("--raw-only")
        if self.cb_noclust.isChecked():
            bits.append("--disable-clustering")
        if self.cb_tof.isChecked():
            bits.append("--tof-tdc-reference " + self.c_tof.currentText())
        if self.e_extra.text().strip():
            bits.append(self.e_extra.text().strip())
        if self.cb_tdc.isChecked():
            bits.append("TDC columns (" + self.c_tdcref.currentText() + ")")
        return ", ".join(bits)

    def update_adv_summary(self, *_a):
        text = self.advanced_summary()
        self.lbl_adv.setText(("Advanced: " + text) if text else "")
        self.lbl_adv.setVisible(bool(text))

    def reset_advanced(self):
        if QMessageBox.question(
                self, APP_NAME,
                "Reset every advanced setting to its default?\n\n"
                "Output goes next to the input file, named after it, and no extra "
                "flags are passed to tpx3dump.\n\n"
                "The Luna folder and the queue are left alone."
        ) != QMessageBox.StandardButton.Yes:
            return
        self.rb_beside.setChecked(True)
        self.e_outdir.clear()
        self.e_template.setText(DEFAULT_TEMPLATE)
        self.cb_skip.setChecked(True)
        for w in (self.e_eps_s, self.e_eps_t, self.e_ntb, self.e_tbi, self.e_extra):
            w.clear()
        self.c_log.setCurrentText("")
        self.cb_raw.setChecked(False)
        self.cb_noclust.setChecked(False)
        self.cb_tof.setChecked(False)
        self.c_tof.setCurrentText(TOF_TDC_REFERENCES[0])
        self.cb_tdc.setChecked(False)
        self.c_tdcref.setCurrentText(TDC_REFERENCES[0])
        self.recompute_outputs()
        self.log("Advanced settings reset to defaults.")

    def remove_any(self):
        """One Remove button for whichever list has a selection."""
        if self.ftable.selectionModel().selectedRows():
            self.remove_folders()
        elif self.jtable.selectionModel().selectedRows():
            self.remove_selected()
        else:
            QMessageBox.information(self, APP_NAME,
                                    "Select a row first -- either a folder on the "
                                    "left or a file on the right.")

    # -- logging ----------------------------------------------------------

    def log(self, text=""):
        self.log_view.appendPlainText(text)
        bar = self.log_view.verticalScrollBar()
        bar.setValue(bar.maximum())

    # -- Luna install -----------------------------------------------------

    DLG = QFileDialog.Option.DontUseNativeDialog   # so dialogs follow the theme

    def pick_luna(self):
        d = QFileDialog.getExistingDirectory(
            self, "Select the Luna installation folder (containing bin/tpx3dump)",
            self.e_luna.text() or str(Path.home()), self.DLG)
        if d:
            self.e_luna.setText(d)
            self.refresh_backend()

    def refresh_backend(self):
        try:
            self.backend = detect_backend(self.e_luna.text())
        except Exception as exc:
            self.backend = Backend(detail=str(exc))
        ok = self.backend.usable
        self.lbl_backend.setText(("OK  " if ok else "!   ") + self.backend.detail)
        self.lbl_backend.setProperty("role", "ok" if ok else "error")
        # The main tab gets one short line; the detail stays on Advanced.
        if ok:
            self.lbl_status.setText(
                "Ready - tpx3dump runs " +
                ("through WSL." if self.backend.kind == "wsl" else "natively."))
            self.lbl_status.setProperty("role", "ok")
            self.b_setup.setVisible(False)
        else:
            self.lbl_status.setText(self.backend.detail)
            self.lbl_status.setProperty("role", "error")
            self.b_setup.setVisible(True)
        for w in (self.lbl_backend, self.lbl_status):
            w.style().unpolish(w)
            w.style().polish(w)

    def check_install(self):
        self.refresh_backend()
        self.log("=" * 78)
        self.log("Backend: " + self.backend.kind + " -- " + self.backend.detail)
        if not self.backend.usable:
            self.log("Cannot execute tpx3dump here. 'Preview commands' and "
                     "'Export .sh' still work.")
            return
        for args in (["--version"], ["process", "--help"]):
            self.log("")
            self.log("$ " + self.backend.display(args))
            try:
                r = subprocess.run(self.backend.argv(args), capture_output=True,
                                   text=True, errors="replace", timeout=120,
                                   creationflags=_NO_WINDOW)
                self.log((r.stdout or "") + (r.stderr or ""))
            except Exception as exc:
                self.log("failed: " + str(exc))

    # -- queue management -------------------------------------------------

    def add_files(self):
        paths, _ = QFileDialog.getOpenFileNames(
            self, "Select .tpx3 files",
            self.cfg.get("last_input", str(Path.home())),
            "Timepix3 raw (*.tpx3);;All files (*)", "", self.DLG)
        if paths:
            self.cfg["last_input"] = str(Path(paths[0]).parent)
            self._add([Path(p) for p in paths])

    @staticmethod
    def _scan_folder(path, recursive=True):
        """Every .tpx3 file in one folder, sorted, case-insensitive suffix."""
        p = Path(path)
        found = set()
        for pat in ("*.tpx3", "*.TPX3"):
            try:
                found.update(p.rglob(pat) if recursive else p.glob(pat))
            except Exception:
                pass
        return sorted((f for f in found if f.is_file()), key=lambda f: str(f).lower())

    def add_folders(self, paths, recursive=True):
        """Append folders to the batch and queue whatever they contain."""
        known = {f["path"] for f in self.folders}
        added = 0
        for raw in paths:
            try:
                p = str(Path(str(raw).strip().strip('"').strip("'")))
            except Exception:
                continue
            if not p or p in known:
                continue
            if not Path(p).is_dir():
                self.log("Not a folder, ignored: " + p)
                continue
            known.add(p)
            self.folders.append({"path": p, "recursive": bool(recursive), "count": None})
            added += 1
        if added:
            self.scan_folders()
        else:
            self.folder_model.reset()
        return added

    def scan_folders(self):
        """Full rescan: new files, vanished files, and re-read metadata.

        Re-reading matters. _add() skips paths already queued, so a job's
        context is captured once, the first time the file is seen. Queue a
        measurement that is still running and there is no
        measurement_metadata.json yet, so every placeholder is empty and the
        name falls back to the bare ASI stem -- and it would stay that way for
        good, because Rescan used to add new files and nothing else.
        """
        if not self.folders:
            self.folder_model.reset()
            return
        new = 0
        for entry in self.folders:
            if not Path(entry["path"]).is_dir():
                entry["count"] = -1          # drive unplugged, folder renamed...
                continue
            files = self._scan_folder(entry["path"], entry["recursive"])
            entry["count"] = len(files)
            new += self._add(files, origin=entry["path"], quiet=True)
        gone = self._prune_missing()
        renamed = self._refresh_metadata()
        self.folder_model.reset()
        self.recompute_outputs()
        missing = sum(1 for f in self.folders if f["count"] == -1)
        empty = sum(1 for f in self.folders if f["count"] == 0)
        msg = (f"Scanned {len(self.folders)} folder(s): {len(self.jobs)} file(s) queued"
               + (f", {new} new" if new else ""))
        if renamed:
            msg += f", {renamed} metadata refresh(es)"
        if gone:
            msg += f", {gone} vanished file(s) dropped"
        if empty:
            msg += f", {empty} folder(s) with no .tpx3"
        if missing:
            msg += f", {missing} folder(s) NOT FOUND"
        self.log(msg)

    def _refresh_metadata(self):
        """Re-read measurement metadata for every job that is not running.

        A running job is skipped because its output path is already on the
        tpx3dump command line -- renaming it underneath would leave the queue
        describing a file the process is not writing.
        """
        changed = 0
        for job in self.jobs:
            if job.status == "running":
                continue
            try:
                ctx = measurement_context(job.src)
            except Exception:
                continue                 # unreadable metadata: keep what we had
            if ctx != job.ctx:
                job.ctx = ctx
                changed += 1
        return changed

    def _prune_missing(self):
        """Drop rows whose input file has disappeared since it was queued.

        Only ones still waiting: a done or failed row is a record of something
        that already happened and is not the rescan's to erase.
        """
        keep = [j for j in self.jobs
                if j.status not in ("queued", "CLASH") or j.src.is_file()]
        gone = len(self.jobs) - len(keep)
        if gone:
            self.jobs[:] = keep
        return gone

    def remove_folders(self):
        rows = [i.row() for i in self.ftable.selectionModel().selectedRows()]
        if not rows:
            QMessageBox.information(self, APP_NAME,
                                    "Select one or more folders in the "
                                    "'Folders to process' list first.")
            return
        drop = {self.folders[r]["path"] for r in rows}
        self.folders = [f for f in self.folders if f["path"] not in drop]
        # Only drop the files that folder contributed; hand-picked files stay.
        self.jobs = [j for j in self.jobs if j.origin not in drop]
        self.folder_model.reset()
        self.recompute_outputs()
        self.log(f"Removed {len(drop)} folder(s); {len(self.jobs)} file(s) left queued.")

    def add_folders_dialog(self):
        dlg = QDialog(self)
        dlg.setWindowTitle("Add folders to the batch")
        dlg.resize(820, 500)
        lay = QVBoxLayout(dlg)
        lay.setSpacing(8)

        head = QLabel("Every folder listed here is searched for .tpx3 files, and each "
                      "one found is queued.\nWith the default output settings the "
                      ".hdf5 is written next to its .tpx3, in that same folder.")
        head.setProperty("muted", True)
        lay.addWidget(head)

        lay.addWidget(QLabel("Folders:"))
        lst = QListWidget()
        lst.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        lay.addWidget(lst, 2)

        def browse():
            d = QFileDialog.getExistingDirectory(
                dlg, "Select a folder (repeat for more)",
                self.cfg.get("last_input", str(Path.home())), self.DLG)
            if d:
                self.cfg["last_input"] = d
                if not lst.findItems(d, Qt.MatchFlag.MatchExactly):
                    lst.addItem(d)

        def drop_selected():
            for item in lst.selectedItems():
                lst.takeItem(lst.row(item))

        hint = QLabel("(Browse can be clicked repeatedly)")
        hint.setProperty("faint", True)
        lay.addWidget(row(button("Browse...", browse),
                          button("Remove selected", drop_selected), hint, None))

        lay.addWidget(QLabel("...or paste paths, one per line:"))
        paste = QPlainTextEdit()
        paste.setFixedHeight(120)
        lay.addWidget(paste, 1)

        cb_rec = QCheckBox("Search subfolders (needed for the ASI "
                           "<measurement>/raw/ layout)")
        cb_rec.setChecked(True)
        lay.addWidget(cb_rec)

        bb = QDialogButtonBox()
        b_add = bb.addButton("Add to batch", QDialogButtonBox.ButtonRole.AcceptRole)
        b_add.setProperty("accent", True)
        bb.addButton("Cancel", QDialogButtonBox.ButtonRole.RejectRole)
        bb.accepted.connect(dlg.accept)
        bb.rejected.connect(dlg.reject)
        lay.addWidget(bb)
        lst.itemDoubleClicked.connect(lambda _i: drop_selected())

        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        paths = [lst.item(i).text() for i in range(lst.count())]
        paths += [ln for ln in paste.toPlainText().splitlines() if ln.strip()]
        if paths and not self.add_folders(paths, cb_rec.isChecked()):
            QMessageBox.information(self, APP_NAME,
                                    "Nothing added - those folders were already in "
                                    "the batch, or are not folders.")

    def _add(self, paths, origin="", quiet=False):
        known = {j.src.resolve() for j in self.jobs}
        added = 0
        for p in paths:
            try:
                rp = p.resolve()
            except Exception:
                rp = p
            if rp in known or not p.is_file():
                continue
            known.add(rp)
            self.jobs.append(Job(src=p, ctx=measurement_context(p), origin=origin))
            added += 1
        if not quiet:
            self.recompute_outputs()
            self.log(f"Added {added} file(s); queue now has {len(self.jobs)}.")
        return added

    def remove_selected(self):
        rows = {i.row() for i in self.jtable.selectionModel().selectedRows()}
        if not rows:
            return
        self.jobs = [j for i, j in enumerate(self.jobs) if i not in rows]
        self.recompute_outputs()

    def clear_queue(self):
        self.jobs = []
        self.folders = []
        self.folder_model.reset()
        self.recompute_outputs()

    def common_root(self):
        """Deepest folder shared by every queued input (for mirror mode)."""
        if not self.jobs:
            return None
        try:
            return Path(os.path.commonpath([str(j.src.parent) for j in self.jobs]))
        except Exception:
            return self.jobs[0].src.parent

    def recompute_outputs(self):
        mode = self.out_mode()
        self.e_outdir.setEnabled(mode != "beside")
        self.b_outdir.setEnabled(mode != "beside")
        template = self.e_template.text().strip() or DEFAULT_TEMPLATE
        outdir = Path(self.e_outdir.text()) if self.e_outdir.text().strip() else None
        root = self.common_root() if mode == "mirror" else None

        for job in self.jobs:
            name = render_name(template, job.ctx) + ".hdf5"
            if mode == "beside" or outdir is None:
                job.dst = job.src.with_name(name)
            elif mode == "flat":
                job.dst = outdir / name
            else:
                try:
                    rel = job.src.parent.relative_to(root)
                except Exception:
                    rel = Path()
                # ASI stores the binary in <measurement>/raw/; recreating that
                # level under the output root adds nothing, so drop it.
                if rel.name.lower() == "raw":
                    rel = rel.parent
                job.dst = outdir / rel / name

        # Flag collisions - two inputs mapping to one output would silently
        # clobber each other, which is the whole thing a rename tool must avoid.
        seen = {}
        for job in self.jobs:
            seen.setdefault(str(job.dst).lower(), []).append(job)
        for group in seen.values():
            if len(group) > 1:
                for job in group:
                    if job.status == "queued":
                        job.status = "CLASH"
                        job.note = "several inputs map to this output name"
            elif group[0].status == "CLASH":
                group[0].status, group[0].note = "queued", ""
        # An Overwrite tick belongs to one output path. Once the template or
        # the output folder moves a job somewhere nothing exists yet, the tick
        # has nothing to refer to, so drop it rather than let it linger.
        for job in self.jobs:
            if job.overwrite and not self.job_clobbers(job):
                job.overwrite = False
        self.job_model.reset()
        self.sync_overwrite_header()
        self.lbl_prog.setText("")
        self.pb.setValue(0)
        self.pb.setTextVisible(False)
        self.pb.setVisible(False)

    def job_clobbers(self, job) -> bool:
        """True when running this job would land on an .hdf5 that is there."""
        if not job.dst or job.status == "CLASH":
            return False
        try:
            return job.dst.exists()
        except Exception:
            return False

    def overwritable_jobs(self):
        return [j for j in self.jobs if self.job_clobbers(j)]

    def sync_overwrite_header(self):
        """Master checkbox reflects the rows: all / some / none ticked."""
        rows = self.overwritable_jobs()
        ticked = sum(1 for j in rows if j.overwrite)
        if not rows or ticked == 0:
            state = Qt.CheckState.Unchecked
        elif ticked == len(rows):
            state = Qt.CheckState.Checked
        else:
            state = Qt.CheckState.PartiallyChecked
        if getattr(self, "jhead", None):
            self.jhead.set_state(state)

    def toggle_all_overwrite(self):
        """Header checkbox: tick every row that has an output to overwrite."""
        rows = self.overwritable_jobs()
        if not rows:
            self.log("Nothing in the queue would overwrite an existing .hdf5.")
            return
        want = not all(j.overwrite for j in rows)
        for job in rows:
            job.overwrite = want
        self.job_model.overwrite_column_changed()
        self.sync_overwrite_header()
        self.log(("Overwrite ticked on " if want else "Overwrite cleared on ")
                 + f"{len(rows)} file(s) whose output already exists.")

    def _job_double_clicked(self, index):
        job = self.jobs[index.row()]
        if job.dst and job.dst.exists():
            self.e_h5.setText(str(job.dst))
            self.tabs.setCurrentWidget(self.tab_inspect)
            self.open_h5()

    def pick_outdir(self):
        d = QFileDialog.getExistingDirectory(
            self, "Select the output folder",
            self.e_outdir.text() or str(Path.home()), self.DLG)
        if d:
            self.e_outdir.setText(d)
            self.recompute_outputs()

    def template_presets(self):
        presets = PRESET_TEMPLATES
        dlg = QDialog(self)
        dlg.setWindowTitle("Name templates")
        dlg.resize(660, 260)
        lay = QVBoxLayout(dlg)
        lay.addWidget(QLabel("Double-click a template to use it:"))
        lst = QListWidget()
        for tmpl, example in presets:
            lst.addItem(f"{tmpl:34s} ->  {example}")
        lay.addWidget(lst, 1)
        bb = QDialogButtonBox()
        b_use = bb.addButton("Use", QDialogButtonBox.ButtonRole.AcceptRole)
        b_use.setProperty("accent", True)
        bb.addButton("Cancel", QDialogButtonBox.ButtonRole.RejectRole)
        bb.accepted.connect(dlg.accept)
        bb.rejected.connect(dlg.reject)
        lay.addWidget(bb)
        lst.itemDoubleClicked.connect(lambda _i: dlg.accept())
        if dlg.exec() == QDialog.DialogCode.Accepted and lst.currentRow() >= 0:
            self.e_template.setText(presets[lst.currentRow()][0])
            self.recompute_outputs()

    # -- command construction --------------------------------------------

    def tpx3dump_args(self, job, backend=None):
        b = backend or self.backend
        args = ["process", "-i", b.translate(job.src), "-o", b.translate(job.dst)]
        for flag, getter in (("--eps-s", self.e_eps_s.text),
                             ("--eps-t", self.e_eps_t.text),
                             ("--num-time-bins", self.e_ntb.text),
                             ("--time-bin-interval", self.e_tbi.text),
                             ("--log-level", self.c_log.currentText)):
            val = getter().strip()
            if val:
                args += [flag, val]
        if self.cb_raw.isChecked():
            args.append("--raw-only")
        if self.cb_noclust.isChecked():
            args.append("--disable-clustering")
        if self.cb_tof.isChecked():
            args += ["--tof-tdc-reference", self.c_tof.currentText()]
        extra = self.e_extra.text().strip()
        if extra:
            args += shlex.split(extra, posix=True)
        return args

    def runnable_jobs(self):
        out = []
        for i, job in enumerate(self.jobs):
            if job.status == "CLASH":
                continue
            if (self.cb_skip.isChecked() and not job.overwrite
                    and job.dst and job.dst.exists()):
                job.status, job.note = "skipped", "output exists"
                self.job_model.row_changed(i)
                continue
            out.append(i)
        return out

    def preview(self):
        if not self.jobs:
            QMessageBox.information(self, APP_NAME, "The queue is empty.")
            return
        self.log("=" * 78)
        self.log(f"{len(self.jobs)} job(s), backend = {self.backend.kind}")
        b = self.backend if self.backend.usable else Backend("native", "tpx3dump")
        for job in self.jobs:
            if job.status == "CLASH":
                self.log("# SKIPPED (name clash): " + job.src.name)
                continue
            self.log(b.display(self.tpx3dump_args(job, b)))
        self.log()

    def export_sh(self):
        if not self.jobs:
            QMessageBox.information(self, APP_NAME, "The queue is empty.")
            return
        path, _ = QFileDialog.getSaveFileName(
            self, "Save a shell script to run on Linux", "run_tpx3dump.sh",
            "Shell script (*.sh)", "", self.DLG)
        if not path:
            return
        b = Backend("native", "tpx3dump")

        def posix(p):
            return win_to_wsl(str(p)) if IS_WINDOWS else str(p)

        jobs = [j for j in self.jobs if j.status != "CLASH"]
        in_root = posix(self.common_root() or "/")
        try:
            out_root = posix(os.path.commonpath([str(j.dst.parent) for j in jobs]))
        except Exception:
            out_root = in_root

        def under(p, root_posix, var):
            """Rewrite an absolute path as "$VAR/relative" where possible."""
            pp = posix(p)
            if root_posix != "/" and pp.startswith(root_posix + "/"):
                return "\"$" + var + "\"/" + shlex.quote(pp[len(root_posix) + 1:])
            return shlex.quote(pp)

        lines = ["#!/usr/bin/env bash",
                 "# Generated by " + APP_NAME + " (Qt) -- run this on the Linux machine.",
                 "#",
                 "# 1. Put the Luna bin/ directory on PATH, or set TPX3DUMP below",
                 "#    to the absolute path of the tpx3dump executable.",
                 "# 2. Edit IN_ROOT / OUT_ROOT to match where the data lives there.",
                 "set -euo pipefail", "",
                 "TPX3DUMP=${TPX3DUMP:-tpx3dump}",
                 "IN_ROOT=" + shlex.quote(in_root),
                 "OUT_ROOT=" + shlex.quote(out_root), ""]
        for job in self.jobs:
            if job.status == "CLASH":
                lines.append("# skipped (name clash): " + job.src.name)
                continue
            src = under(job.src, in_root, "IN_ROOT")
            dst = under(job.dst, out_root, "OUT_ROOT")
            tail = [shlex.quote(a) for a in self.tpx3dump_args(job, b)[5:]]
            lines.append('mkdir -p "$(dirname ' + dst + ')"')
            lines.append(" ".join(['"$TPX3DUMP"', "process", "-i", src, "-o", dst] + tail))
        try:
            Path(path).write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")
        except Exception as exc:
            QMessageBox.critical(self, APP_NAME, "Could not write the script:\n" + str(exc))
            return
        self.log("Wrote " + path)

    # -- running (QProcess, one job at a time) ----------------------------

    def run_queue(self):
        self.refresh_backend()
        if not self.backend.usable:
            QMessageBox.critical(
                self, APP_NAME,
                "tpx3dump cannot be executed here.\n\n" + self.backend.detail +
                "\n\nSet the Luna folder on the Advanced tab, or use its "
                "'Export .sh' button to run this queue on a Linux machine.")
            return
        if not self.jobs:
            QMessageBox.information(self, APP_NAME, "The queue is empty.")
            return
        if self.out_mode() != "beside" and not self.e_outdir.text().strip():
            QMessageBox.critical(self, APP_NAME,
                                 "Choose an output folder on the Advanced tab, or "
                                 "switch back to 'Next to the input file'.")
            return
        clashes = [j for j in self.jobs if j.status == "CLASH"]
        if clashes:
            QMessageBox.warning(
                self, APP_NAME,
                f"{len(clashes)} input(s) map to a duplicated output name and will "
                "be skipped.\nAdd {measurement} or {datetime} to the template to "
                "make the names unique.")
        for i, job in enumerate(self.jobs):
            if job.status in ("done", "failed", "skipped"):
                job.status, job.note = "queued", ""
                self.job_model.row_changed(i)
        todo = self.runnable_jobs()
        if not todo:
            self.log("Nothing to do - every output already exists. "
                     "Tick 'Overwrite' in the queue to redo one anyway.")
            return
        if not self.check_wsl_drives(todo):
            for i, job in enumerate(self.jobs):
                if job.status == "queued":
                    self.job_model.row_changed(i)
            return

        self.save_settings()
        self.b_run.setEnabled(False)
        self.b_stop.setEnabled(True)
        self.stopping = False
        self.todo = list(todo)
        self.total = len(self.todo)
        self.done = self.ok = self.failed = 0
        self.pb.setMaximum(self.total)
        self.pb.setValue(0)
        self.pb.setTextVisible(True)
        self.pb.setVisible(True)
        self.lbl_prog.setText(f"0 / {self.total}")
        self.log("=" * 78)
        self.log(f"Running {self.total} job(s) via {self.backend.kind}")
        self.t_all = time.time()
        self._start_next()

    def check_wsl_drives(self, todo) -> bool:
        """Make sure WSL can actually see the data this run touches.

        WSL auto-mounts fixed disks only, so a USB stick or another removable
        volume is invisible to tpx3dump: it logs a "Skipping file" warning and
        then panics with "index out of bounds: the len is 0". Mounting takes
        one root command and no password, so offer that instead of letting the
        run crash. Returns False when the run should not start.
        """
        if self.backend.kind != "wsl":
            return True

        NL = chr(10)
        letters, inputs = set(), []
        for i in todo:
            job = self.jobs[i]
            inputs.append(self.backend.translate(job.src))
            for path in (job.src, job.dst.parent if job.dst else None):
                if path is not None:
                    letter = drive_letter(path)
                    if letter:
                        letters.add(letter)

        missing = wsl_unmounted_drives(letters)
        if missing:
            names = ", ".join(d.upper() + ":" for d in missing)
            plural = "drives are" if len(missing) > 1 else "drive is"
            if QMessageBox.question(
                    self, APP_NAME,
                    names + " cannot be reached from WSL." + NL + NL +
                    "WSL mounts fixed disks automatically but leaves removable "
                    "ones (USB sticks, card readers, some external drives) "
                    "alone, so the " + plural + " simply not there as far as "
                    "tpx3dump is concerned -- it would skip every file and then "
                    "crash with 'index out of bounds'." + NL + NL +
                    "Mount it now? This needs no password, and lasts until WSL "
                    "next shuts down.") != QMessageBox.StandardButton.Yes:
                self.log("Run cancelled -- " + names + " is not mounted in WSL.")
                return False
            for letter in missing:
                ok, err = wsl_mount_drive(letter)
                self.log(("Mounted " if ok else "Could not mount ") +
                         letter.upper() + ": at /mnt/" + letter +
                         ("" if ok else " -- " + err))
            missing = wsl_unmounted_drives(letters)

        if not missing:
            missing_files = wsl_missing_paths(inputs)
            if not missing_files:
                return True
            shown = missing_files[:6]
            QMessageBox.critical(
                self, APP_NAME,
                str(len(missing_files)) + " input file(s) exist on Windows but "
                "not inside WSL:" + NL + NL +
                NL.join("    " + f for f in shown) +
                (NL + "    ..." if len(missing_files) > len(shown) else "") +
                NL + NL +
                "tpx3dump would skip them and then crash. Check the drive is "
                "still connected, or copy the data to an internal disk.")
            self.log("Run cancelled -- WSL cannot see " +
                     str(len(missing_files)) + " input file(s).")
            return False

        QMessageBox.critical(
            self, APP_NAME,
            "Still cannot reach " + ", ".join(d.upper() + ":" for d in missing) +
            " from WSL." + NL + NL +
            "Mount it by hand in a WSL terminal:" + NL +
            NL.join("    sudo mkdir -p /mnt/{0} && "
                    "sudo mount -t drvfs {1}: /mnt/{0}".format(d, d.upper())
                    for d in missing) + NL + NL +
            "Or copy the data onto an internal disk (C: or D:) and rescan.")
        return False

    def _start_next(self):
        if self.stopping or not self.todo:
            self._finish()
            return
        idx = self.todo.pop(0)
        self.cur = idx
        self._settled = False
        job = self.jobs[idx]
        job.status, job.note = "running", ""
        self.job_model.row_changed(idx)
        self.jtable.scrollTo(self.job_model.index(idx, 0))
        try:
            job.dst.parent.mkdir(parents=True, exist_ok=True)
            argv = self.backend.argv(self.tpx3dump_args(job))
        except Exception as exc:
            self._job_done(idx, -1, str(exc))
            return

        self.log("")
        self.log(f"[{self.done + 1}/{self.total}] {job.src.name}  ->  {job.dst.name}")
        self.log("$ " + " ".join(shlex.quote(a) for a in argv))
        self.t_job = time.time()

        p = QProcess(self)
        p.setProcessChannelMode(QProcess.ProcessChannelMode.MergedChannels)
        p.readyReadStandardOutput.connect(self._read_proc)
        p.finished.connect(lambda code, _st, i=idx: self._job_done(i, code, ""))
        p.errorOccurred.connect(lambda err, i=idx: self._proc_error(i, err))
        self.proc = p
        p.start(argv[0], argv[1:])

    def _read_proc(self):
        if not self.proc:
            return
        chunk = bytes(self.proc.readAllStandardOutput()).decode("utf-8", "replace")
        for line in chunk.splitlines():
            self.log("  " + line.rstrip())

    def _proc_error(self, idx, err):
        # Only FailedToStart needs handling here; every other error is followed
        # by finished(), which settles the job normally.
        if err == QProcess.ProcessError.FailedToStart:
            msg = "executable not found or not runnable"
            self.log("  " + msg)
            self._job_done(idx, -1, msg)

    def _job_done(self, idx, code, err):
        if getattr(self, "_settled", True):
            return                      # finished() and errorOccurred() can both fire
        self._settled = True
        if self.proc is not None:
            self.proc.deleteLater()
            self.proc = None
        job = self.jobs[idx]
        dt = time.time() - self.t_job

        if self.stopping and code != 0:
            job.status, job.note = "queued", "cancelled"
        elif err:
            job.status, job.note = "failed", err
            self.failed += 1
        elif code == 0 and job.dst.exists():
            size = human_size(job.dst.stat().st_size)
            job.status, job.note = "done", f"{size} in {dt:.1f}s"
            self.log(f"  OK  {size} in {dt:.1f} s")
            self.ok += 1
            job.note += self._tag_output(job)
        elif code == 0:
            job.status, job.note = "failed", "exit 0 but no output file"
            self.failed += 1
        else:
            job.status, job.note = "failed", f"exit code {code}"
            self.failed += 1

        self.job_model.row_changed(idx)
        self.sync_overwrite_header()
        self.done += 1
        self.pb.setValue(self.done)
        self.lbl_prog.setText(f"{self.done} / {self.total}")
        QTimer.singleShot(0, self._start_next)

    def _tag_output(self, job):
        """Post-process one finished output: write its TDC columns.

        Runs inline between jobs on purpose -- it is the same sequential batch
        the user started, and doing it here means the file is complete before
        the queue moves on. Never fails the job: the .hdf5 tpx3dump wrote is
        good either way, so a TDC problem is reported and the run continues.
        """
        if not self.cb_tdc.isChecked():
            return ""
        ref = self.c_tdcref.currentText()
        try:
            res = add_tdc_columns(job.dst, ref, log=self.log)
        except Exception as exc:
            self.log("  TDC columns skipped: " + str(exc))
            return ", no TDC"
        tagged = sum(v["tagged"] for v in res.values())
        return f", TDC {ref} ({tagged:,} rows)"

    def _finish(self):
        self.b_run.setEnabled(True)
        self.b_stop.setEnabled(False)
        # Every job just written is now something a rerun would overwrite.
        self.job_model.overwrite_column_changed()
        self.sync_overwrite_header()
        if self.stopping:
            self.log("Stopped by user.")
        self.log(f"Finished: {self.ok} ok, {self.failed} failed, "
                 f"{self.total - self.done} not run, "
                 f"{time.time() - self.t_all:.1f} s total.")
        self.log()

    def stop_run(self):
        self.stopping = True
        self.todo = []
        self.log("Stop requested - terminating the current tpx3dump...")
        if self.proc is not None:
            self.proc.kill()

    # -- settings ---------------------------------------------------------

    def save_settings(self):
        self.cfg.update({
            "luna_dir": self.e_luna.text(), "out_mode": self.out_mode(),
            "out_dir": self.e_outdir.text(), "template": self.e_template.text(),
            "skip_existing": self.cb_skip.isChecked(),
            "eps_s": self.e_eps_s.text(), "eps_t": self.e_eps_t.text(),
            "num_time_bins": self.e_ntb.text(),
            "time_bin_interval": self.e_tbi.text(),
            "log_level": self.c_log.currentText(),
            "raw_only": self.cb_raw.isChecked(),
            "disable_clustering": self.cb_noclust.isChecked(),
            "tof_tdc_reference_on": self.cb_tof.isChecked(),
            "tof_tdc_reference": self.c_tof.currentText(),
            "tdc_columns": self.cb_tdc.isChecked(),
            "tdc_reference": self.c_tdcref.currentText(),
            "extra": self.e_extra.text(),
            "theme": self.theme_name,
            "folders": [{"path": f["path"], "recursive": f["recursive"]}
                        for f in self.folders],
        })
        save_config(self.cfg)

    def closeEvent(self, event):
        if self.proc is not None:
            if QMessageBox.question(
                    self, APP_NAME,
                    "A run is still in progress. Stop it and quit?"
            ) != QMessageBox.StandardButton.Yes:
                event.ignore()
                return
            self.stop_run()
        self.save_settings()
        event.accept()

    # -- inspect tab ------------------------------------------------------

    def _build_inspect(self, tab):
        lay = QVBoxLayout(tab)
        lay.setContentsMargins(10, 12, 10, 10)
        lay.setSpacing(8)

        self.e_h5 = QLineEdit()
        lay.addWidget(row("HDF5 file:", self.e_h5,
                          button("Browse...", self.pick_h5),
                          button("Open", self.open_h5),
                          button("Use selected output", self.inspect_selected_output)))

        cap = QLabel("Datasets")
        cap.setProperty("muted", True)
        lay.addWidget(cap)
        self.itable = QTableWidget(0, 5)
        self.itable.setHorizontalHeaderLabels(
            ["Name", "Shape", "Dtype", "Chunks", "Compression"])
        self.itable.verticalHeader().setVisible(False)
        self.itable.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        ihdr = self.itable.horizontalHeader()
        ihdr.setDefaultAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        ihdr.setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        self.itable.setShowGrid(False)
        self.itable.setAlternatingRowColors(True)
        lay.addWidget(self.itable, 1)

        lay.addWidget(row(
            button("Hitmap, pixels", lambda: self.plot("hitmap")),
            button("Hitmap, clusters", lambda: self.plot("cmap")),
            button("ToT, peak pixel", lambda: self.plot("tot")),
            button("ToT, cluster total", lambda: self.plot("stot")),
            button("Cluster size histogram", lambda: self.plot("csize")),
            button("Time since TDC edge", lambda: self.plot("tdc")),
            None))

        self.c_tdcref_i = QComboBox()
        self.c_tdcref_i.addItems(TDC_REFERENCES)
        self.c_tdcref_i.setCurrentText(self.cfg.get("tdc_reference",
                                                    TDC_REFERENCES[0]))
        self.c_tdcref_i.setToolTip(
            "Which TDC edge starts the clock. Shared with the same setting on "
            "the Advanced tab.")
        lay.addWidget(row(
            QLabel("TDC reference:"), self.c_tdcref_i,
            button("Add TDC columns to this file", self.write_tdc_columns),
            button("Preview frame", self.preview_tdc_frame),
            None))

        self.isum = QPlainTextEdit()
        self.isum.setReadOnly(True)
        self.isum.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        lay.addWidget(self.isum, 1)

    def pick_h5(self):
        p, _ = QFileDialog.getOpenFileName(
            self, "Select an HDF5 file", self.cfg.get("last_h5", ""),
            "HDF5 (*.hdf5 *.h5);;All files (*)", "", self.DLG)
        if p:
            self.cfg["last_h5"] = str(Path(p).parent)
            self.e_h5.setText(p)
            self.open_h5()

    def inspect_selected_output(self):
        rows = self.jtable.selectionModel().selectedRows()
        if not rows:
            QMessageBox.information(self, APP_NAME,
                                    "Select a row in the Process queue first.")
            return
        job = self.jobs[rows[0].row()]
        if not job.dst or not job.dst.exists():
            QMessageBox.information(self, APP_NAME, "That job has no output file yet.")
            return
        self.e_h5.setText(str(job.dst))
        self.open_h5()

    def open_h5(self):
        h5py, np = require_h5py(self)
        if h5py is None:
            return
        path = Path(self.e_h5.text())
        self.itable.setRowCount(0)
        self.isum.clear()
        if not path.is_file():
            self.isum.setPlainText("No such file: " + str(path))
            return
        try:
            with h5py.File(path, "r") as f:
                rows, lines = [], [str(path),
                                   "file size: " + human_size(path.stat().st_size)]
                if dict(f.attrs):
                    lines.append("root attributes: " + str(dict(f.attrs)))

                def visit(name, obj):
                    if isinstance(obj, h5py.Dataset):
                        rows.append((name, str(obj.shape), str(obj.dtype),
                                     str(obj.chunks), str(obj.compression)))
                f.visititems(visit)
                self.itable.setRowCount(len(rows))
                for r, vals in enumerate(rows):
                    for c, v in enumerate(vals):
                        self.itable.setItem(r, c, QTableWidgetItem(v))
                self.itable.resizeColumnsToContents()

                lines.append("")
                for key, label in (("PixelHits", "pixel hits"), ("Clusters", "clusters")):
                    if key in f:
                        n = f[key].shape[0]
                        lines.append(f"{label:14s} {n:,}")
                        if n:
                            lines.append("   fields: " + ", ".join(f[key].dtype.names or ()))
                if "PixelHits" in f and f["PixelHits"].shape[0]:
                    ph = f["PixelHits"]
                    head = ph[: min(200000, ph.shape[0])]
                    toa = head["toa"].astype("float64")
                    lines.append(f"   toa range (first {len(head):,} rows): "
                                 f"{toa.min():.0f} .. {toa.max():.0f}")
                    lines.append(f"   x range {head['x'].min()}..{head['x'].max()}   "
                                 f"y range {head['y'].min()}..{head['y'].max()}")
                    if "tof" in (ph.dtype.names or ()):
                        valid = int((head["tof"] >= 0).sum())
                        lines.append(f"   tof: {valid:,} of {len(head):,} rows are >= 0 "
                                     + ("(ToF was computed)" if valid else
                                        "(no TDC reference -> ToF unset)"))
                if "Clusters" in f and f["Clusters"].shape[0]:
                    cl = f["Clusters"][: min(200000, f["Clusters"].shape[0])]
                    lines.append(f"   mean cluster size (first {len(cl):,}): "
                                 f"{cl['size'].mean():.2f}")
                lines.extend(self._tdc_summary(f, np))
                if "ExposureTimeBoundaries" in f:
                    etb = f["ExposureTimeBoundaries"][:]
                    lines.append(f"exposure time boundaries: {len(etb)} entries, "
                                 f"first {etb[:4].tolist() if len(etb) else []}")
                self.isum.setPlainText("\n".join(lines))
        except Exception:
            self.isum.setPlainText(traceback.format_exc())

    def _tdc_summary(self, f, np):
        """The TDC block of the Inspect summary: edges, rate, columns."""
        events = read_tdc_events(f, np)
        if events is None:
            return ["TDC            /" + TDC_DATASET + " absent "
                    "(tpx3dump predates TDC support, or none was recorded)"]
        raw_n = f[TDC_DATASET].shape[0]
        if len(events) == 0:
            return ["TDC            no edges recorded"]
        out = [f"TDC            {len(events):,} edge(s) "
               f"({raw_n:,} raw records; every chip repeats the packet)",
               "   " + describe_tdc_types(events, np)]
        for name in TOF_TDC_REFERENCES:
            sel = tdc_reference_edges(events, name, np)
            if len(sel) < 2:
                continue
            gaps = np.diff(sel["timestamp"].astype("int64")).astype("float64")
            gaps *= TDC_SECONDS_PER_TICK
            out.append(f"   {name:12s} {len(sel):,} edges, period "
                       f"{gaps.mean() * 1e6:.3f} us "
                       f"(+- {gaps.std() * 1e9:.1f} ns)")
        span = float(events["timestamp"][-1] -
                     events["timestamp"][0]) * TDC_SECONDS_PER_TICK
        out.append(f"   span         {span * 1e3:.3f} ms")
        for src_name, (_tf, col_name) in TDC_SOURCES.items():
            if col_name in f:
                a = f[col_name].attrs
                out.append(f"   /{col_name}: {f[col_name].shape[0]:,} rows, "
                           f"reference {a.get('tdc_reference', '?')}"
                           + ("" if a.get("written_by") == TDC_STAMP
                              else "  [not written by this GUI]"))
        return out

    # -- TDC columns ------------------------------------------------------

    def write_tdc_columns(self):
        """Tag this file's hits and clusters with the TDC edge they follow."""
        h5py, np = require_h5py(self)
        if h5py is None:
            return
        path = Path(self.e_h5.text())
        if not path.is_file():
            QMessageBox.information(self, APP_NAME, "Open an HDF5 file first.")
            return
        ref = self.c_tdcref_i.currentText()
        if QMessageBox.question(
                self, APP_NAME,
                f"Write TDC columns into\n{path.name}\n\n"
                f"Reference: {ref}\n\n"
                "This modifies the file in place. It adds /PixelHitsTDC and "
                "/ClustersTDC; PixelHits, Clusters and TDCEvents are left "
                "exactly as tpx3dump wrote them.\n\nContinue?"
        ) != QMessageBox.StandardButton.Yes:
            return
        self.tabs.setCurrentWidget(self.tab_inspect)
        self.log(f"Adding TDC columns to {path.name} ({ref})")
        try:
            self._busy(True)
            res = add_tdc_columns(path, ref, log=self.log)
        except Exception as exc:
            self.log("  FAILED: " + str(exc))
            QMessageBox.critical(self, APP_NAME,
                                 "Could not write the TDC columns.\n\n" + str(exc))
            return
        finally:
            self._busy(False)
        self.open_h5()          # refresh the dataset table with the new ones
        QMessageBox.information(
            self, APP_NAME,
            "TDC columns written.\n\n" + "\n".join(
                f"/{k}: {v['tagged']:,} of {v['rows']:,} rows tagged"
                for k, v in res.items()))

    def preview_tdc_frame(self):
        """Show the head of the joined frame, so the columns are visible."""
        h5py, np = require_h5py(self)
        if h5py is None:
            return
        pd = require_pandas(self)
        if pd is None:
            return
        path = Path(self.e_h5.text())
        if not path.is_file():
            QMessageBox.information(self, APP_NAME, "Open an HDF5 file first.")
            return
        ROWS = 40
        blocks = []
        try:
            self._busy(True)
            edges = read_tdcs(path)
            blocks.append("read_tdcs() -- the edges themselves, deduplicated\n"
                          + edges.to_string(max_rows=ROWS))
            for which in TDC_SOURCES:
                try:
                    # limit= keeps this instant on a file with 10^8 hits; the
                    # stored columns are used when they are there, so what is
                    # shown is what a full read would give.
                    df = read_with_tdc(path, which, limit=ROWS)
                except ValueError as exc:
                    blocks.append(f"read_with_tdc(..., {which!r}) -- {exc}")
                    continue
                blocks.append(
                    f"read_with_tdc(..., {which!r})   reference "
                    f"{df.attrs['tdc_reference']}, "
                    + ("read from the file" if df.attrs["tdc_from_file"]
                       else "computed on the fly -- not stored yet")
                    + "\n" + df.to_string(max_rows=ROWS))
        except Exception as exc:
            QMessageBox.critical(self, APP_NAME,
                                 "Could not build the frame.\n\n" + str(exc))
            return
        finally:
            self._busy(False)

        dlg = QDialog(self)
        dlg.setWindowTitle(path.name + " -- first %d rows with TDC" % ROWS)
        dlg.resize(1000, 700)
        lay = QVBoxLayout(dlg)
        view = QPlainTextEdit("\n\n".join(blocks))
        view.setReadOnly(True)
        view.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        view.setFont(QFontDatabase.systemFont(QFontDatabase.SystemFont.FixedFont))
        lay.addWidget(view, 1)
        bb = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        bb.rejected.connect(dlg.reject)
        lay.addWidget(bb)
        dlg.show()              # modeless, like the plots
        self._open_plots = getattr(self, "_open_plots", [])
        self._open_plots.append(dlg)

    def _busy(self, on):
        """Hourglass while a synchronous read/write holds the event loop."""
        if on:
            QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        else:
            QApplication.restoreOverrideCursor()
        QApplication.processEvents()

    # -- plots ------------------------------------------------------------

    def plot(self, what):
        h5py, np = require_h5py(self)
        if h5py is None:
            return
        try:
            import matplotlib
            matplotlib.use("QtAgg")
            from matplotlib.figure import Figure
            from matplotlib.backends.backend_qtagg import (
                FigureCanvasQTAgg, NavigationToolbar2QT)
        except Exception:
            QMessageBox.critical(self, APP_NAME,
                                 "matplotlib is required for plots:\n"
                                 "    python -m pip install matplotlib")
            return
        path = Path(self.e_h5.text())
        if not path.is_file():
            QMessageBox.information(self, APP_NAME, "Open an HDF5 file first.")
            return

        CAP = 8_000_000          # rows read at most, keeps the UI responsive
        style_ctx, styled = plot_style_context(self.theme_name)
        with style_ctx:
            fig = Figure(figsize=PLOT_FIGSIZE, dpi=100)
            ax = fig.add_subplot(111)
            if not styled:
                # No komorebi_mpl: paint the figure from the app palette so a
                # dark theme still gets a dark plot.
                fig.patch.set_facecolor(self.pal["surface_container_low"])
                ax.set_facecolor(self.pal["surface"])
                for side in ax.spines.values():
                    side.set_color(self.pal["outline_variant"])
                ax.tick_params(colors=self.pal["text_muted"])
                ax.xaxis.label.set_color(self.pal["text"])
                ax.yaxis.label.set_color(self.pal["text"])
                ax.title.set_color(self.pal["text"])
            ok = self._draw_plot(what, path, fig, ax, styled, CAP, h5py, np)
            if ok:
                fig.tight_layout()
        if not ok:
            return

        dlg = QDialog(self)
        dlg.setWindowTitle(path.name + " -- " + PLOT_TITLES.get(what, what))
        dlg.resize(760, 660)
        lay = QVBoxLayout(dlg)
        canvas = FigureCanvasQTAgg(fig)
        lay.addWidget(NavigationToolbar2QT(canvas, dlg))
        lay.addWidget(canvas, 1)
        dlg.show()          # modeless: compare several plots side by side
        self._open_plots = getattr(self, "_open_plots", [])
        self._open_plots.append(dlg)

    def _draw_plot(self, what, path, fig, ax, styled, CAP, h5py, np):
        """Draw one plot onto ax. Returns False if there was nothing to draw.

        Runs inside the style context so every artist -- including the
        colorbar, which is its own axes -- picks up the style rcParams.
        """
        try:
            with h5py.File(path, "r") as f:
                if what == "tdc":
                    return self._draw_tdc(f, ax, styled, CAP, np)
                # Only the pixel hitmap comes from PixelHits; everything else
                # is a cluster-level quantity and reads Clusters.
                if what == "hitmap":
                    if "PixelHits" not in f or not f["PixelHits"].shape[0]:
                        QMessageBox.information(
                            self, APP_NAME, "This file has no pixel hits "
                                            "(processed with --discard-pixel-data?).")
                        return False
                    d = f["PixelHits"]
                    n = min(CAP, d.shape[0])
                    img = self._accumulate_xy(d, n, np, "x", "y")
                    im = ax.imshow(img, origin="lower", aspect="equal")
                    self._style_colorbar(
                        fig.colorbar(im, ax=ax, label="hits / pixel"), styled)
                    ax.set(title=f"Hitmap, pixels -- {n:,} hits",
                           xlabel="x (pixels)", ylabel="y (pixels)")
                else:
                    if "Clusters" not in f or not f["Clusters"].shape[0]:
                        QMessageBox.information(
                            self, APP_NAME, "This file has no clusters "
                                            "(processed with --disable-clustering?).")
                        return False
                    d = f["Clusters"]
                    n = min(CAP, d.shape[0])
                    if what == "cmap":
                        img = self._accumulate_xy(d, n, np, "cx", "cy")
                        im = ax.imshow(img, origin="lower", aspect="equal")
                        self._style_colorbar(
                            fig.colorbar(im, ax=ax, label="clusters / pixel"),
                            styled)
                        ax.set(title=f"Hitmap, clusters -- {n:,} clusters",
                               xlabel="x (pixels)", ylabel="y (pixels)")
                    elif what == "tot":
                        # Clusters/ctot is the *peak pixel* ToT of the cluster,
                        # not its total -- verified against PixelHits: ctot ==
                        # max(tot) over the cluster's hits for every cluster in
                        # the reference file, and it saturates at exactly the
                        # single-pixel maximum. Clusters/sum_tot is the total;
                        # that is the "stot" plot below.
                        ctot = self._gather(d, n, np, "ctot").astype("float64")
                        # One bin per 40 MHz tick: ctot is quantised to 25 ns,
                        # so this is the finest binning that carries no
                        # aliasing. Edges run to max + one step, so the largest
                        # value lands inside the last bin instead of falling
                        # off the end as it would with arange(0, max, 25).
                        edges = np.arange(0.0, float(ctot.max()) + TOT_LSB_NS,
                                          TOT_LSB_NS)
                        ax.hist(ctot, bins=edges, histtype="step",
                                **self._series_colour(styled))
                        ax.set(title=f"Peak-pixel ToT -- {n:,} clusters",
                               xlabel="ToT (ns)", ylabel="Counts (-)",
                               yscale="log")
                    elif what == "stot":
                        # The cluster's summed ToT: a deposited-charge proxy,
                        # unlike ctot which saturates once the charge starts
                        # spreading to neighbouring pixels instead of driving
                        # the central one higher.
                        stot = self._gather(d, n, np, "sum_tot").astype("float64")
                        hi = float(stot.max())
                        # Still a whole number of 25 ns ticks, just a coarser
                        # one: sum_tot runs to ~227 us and the native tick
                        # would be ~9000 bins.
                        k = max(1, round(hi / TOT_LSB_NS / STOT_TARGET_BINS))
                        step = k * TOT_LSB_NS
                        edges = np.arange(0.0, hi + step, step)
                        ax.hist(stot, bins=edges, histtype="step",
                                **self._series_colour(styled))
                        ax.set(title=f"Cluster total ToT -- {n:,} clusters",
                               xlabel=f"summed ToT (ns)   ({step:g} ns bins)",
                               ylabel="Counts (-)", yscale="log")
                    else:                                   # csize
                        s = self._gather(d, n, np, "size").astype("int64")
                        ax.hist(s, bins=CSIZE_BINS, range=(0, CSIZE_MAX),
                                **self._series_colour(styled))
                        title = f"Cluster size -- {n:,} clusters"
                        over = int((s > CSIZE_MAX).sum())
                        if over:        # never truncate silently
                            title += f"   ({over:,} above {CSIZE_MAX} not shown)"
                        ax.set(title=title, xlabel="Cluster size (-)",
                               ylabel="Counts (-)")
        except Exception:
            QMessageBox.critical(self, APP_NAME, traceback.format_exc())
            return False
        return True

    def _draw_tdc(self, f, ax, styled, CAP, np):
        """Histogram of how long after its TDC edge each cluster arrived.

        Computed from /TDCEvents rather than read from PixelHits/tof, so it
        works whether or not --tof-tdc-reference was passed and whichever
        reference is picked now. Clusters, not hits: one entry per particle.
        """
        events = read_tdc_events(f, np)
        if events is None or len(events) == 0:
            QMessageBox.information(
                self, APP_NAME,
                "This file has no TDC edges to measure from.")
            return False
        ref = self.c_tdcref_i.currentText()
        edges = tdc_reference_edges(events, ref, np)
        if len(edges) == 0:
            QMessageBox.information(
                self, APP_NAME, f"No {ref} edges in this file.\nIt has "
                + describe_tdc_types(events, np) + ".")
            return False
        src = "Clusters" if ("Clusters" in f and f["Clusters"].shape[0]) else "PixelHits"
        if src not in f or not f[src].shape[0]:
            QMessageBox.information(self, APP_NAME,
                                    "This file has no hits or clusters.")
            return False
        field_name = TDC_SOURCES[src][0]
        n = min(CAP, f[src].shape[0])
        times = self._gather(f[src], n, np, field_name)
        cols = tag_times_with_tdc(times, edges, np)
        good = cols["tdc_dt"][cols["tdc_index"] >= 0].astype("float64")
        if not len(good):
            QMessageBox.information(
                self, APP_NAME,
                f"Every row precedes the first {ref} edge, so none of them "
                "has a time to measure.")
            return False
        us = good * (TDC_SECONDS_PER_TICK * 1e6)
        ax.hist(us, bins=200, histtype="step", **self._series_colour(styled))
        dropped = n - len(good)
        title = f"Time since {ref} -- {len(good):,} {src.lower()}"
        if dropped:                 # never truncate silently
            title += f"   ({dropped:,} before the first edge)"
        ax.set(title=title, xlabel="t - t(TDC)  (us)", ylabel="Counts (-)",
               yscale="log")
        return True

    def _series_colour(self, styled):
        """Let the style pick the series colour; override only without one."""
        return {} if styled else {"color": self.pal["primary"]}

    def _style_colorbar(self, cb, styled):
        """Theme the colorbar explicitly.

        A colorbar lives on its own Axes, so none of the theming applied to the
        main axes reaches it -- its ticks and label keep matplotlib default
        near-black and vanish against a dark figure.
        """
        if styled:
            import matplotlib as mpl
            text, tick = mpl.rcParams["text.color"], mpl.rcParams["ytick.color"]
            edge = mpl.rcParams["axes.edgecolor"]
        else:
            text, tick = self.pal["text"], self.pal["text_muted"]
            edge = self.pal["outline_variant"]
        cb.ax.yaxis.label.set_color(text)
        cb.ax.tick_params(colors=tick)
        if cb.outline is not None:
            cb.outline.set_edgecolor(edge)
        return cb

    @staticmethod
    def _gather(dset, n, np, field_name, step=2_000_000):
        parts = [dset[i:min(i + step, n)][field_name] for i in range(0, n, step)]
        return np.concatenate(parts) if parts else np.array([])

    def _accumulate_xy(self, dset, n, np, fx, fy, step=2_000_000):
        """2D histogram built in slices so huge files do not blow up memory."""
        size = 0
        img = None
        for i in range(0, n, step):
            chunk = dset[i:min(i + step, n)]
            x = chunk[fx].astype("int64")
            y = chunk[fy].astype("int64")
            need = int(max(x.max(initial=0), y.max(initial=0))) + 1
            if img is None or need > size:
                new = max(need, 256, size)
                grown = np.zeros((new, new), dtype="int64")
                if img is not None:
                    grown[:size, :size] = img
                img, size = grown, new
            flat = np.bincount(y * size + x, minlength=size * size)
            img += flat.reshape(size, size)
        return img if img is not None else np.zeros((256, 256), dtype="int64")

    # -- window geometry ---------------------------------------------------

    def showEvent(self, event):
        super().showEvent(event)
        if not self._fitted:            # first map only; never fight the user
            self._fitted = True         # once they have resized it themselves
            # Deferred by one event-loop turn on purpose: inside showEvent the
            # frame has not been applied yet and frameGeometry() still returns
            # the bare client rect, so the title bar measures as zero and the
            # window ends up exactly one title bar too tall.
            QTimer.singleShot(0, self._fit_to_screen)

    def _fit_to_screen(self):
        """Shrink and centre the window if its *frame* does not fit the screen.

        The frame -- title bar and resize borders -- is not part of the layout,
        so a client area sized to the work area still hangs off the bottom edge.
        Must run after the window is mapped, where frameGeometry() finally
        reports something real.
        """
        scr = self.screen() or QApplication.primaryScreen()
        if scr is None:
            return
        avail = scr.availableGeometry()
        frame = self.frameGeometry()
        chrome_w = max(0, frame.width() - self.width())
        chrome_h = max(0, frame.height() - self.height())
        # Fractional scaling (125% here) means Qt's logical size does not land
        # on a whole number of physical pixels, so a window sized to exactly
        # the work area still spills a pixel or two. 8 px of slack is cheaper
        # than reasoning about the rounding.
        margin = 8
        self.resize(min(self.width(), avail.width() - chrome_w - margin),
                    min(self.height(), avail.height() - chrome_h - margin))
        frame = self.frameGeometry()
        frame.moveCenter(avail.center())
        self.move(frame.topLeft())
