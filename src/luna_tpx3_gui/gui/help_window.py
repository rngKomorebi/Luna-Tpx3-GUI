"""The Help window: what every tab, option and flag does, inside the app.

Opened from the Help menu or F1. It is one window, hidden rather than
destroyed on close, so it reopens where the reader left off.

The flag reference and the column units are generated from the same tables
the Advanced tab and the row viewer use (FLAG_GROUPS, FIELD_UNITS), so they
cannot drift apart. The prose is written here. The page is rebuilt on a theme
change, since rich text takes its colours from the HTML, not the stylesheet.
"""

from __future__ import annotations

from html import escape

from PySide6.QtCore import Qt
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (QDialog, QHBoxLayout, QLabel, QLineEdit,
                               QListWidget, QTextBrowser, QVBoxLayout)

from .. import __version__
from ..functions.common import APP_NAME
from ..functions.config import CONFIG_PATH
from ..functions.flags import FLAG_GROUPS
from ..functions.naming import DEFAULT_TEMPLATE
from ..functions.plotting import PLOT_TITLES
from .dataset_view import FIELD_UNITS
from .widgets import row

# (anchor, title) in page order; the list on the left is built from this.
SECTIONS = [
    ("start", "Getting started"),
    ("process", "Process tab"),
    ("advanced", "Advanced tab"),
    ("naming", "Name templates"),
    ("flags", "tpx3dump flags"),
    ("inspect", "Inspect HDF5 tab"),
    ("file", "What is in the file"),
    ("tdc", "TDC"),
    ("trouble", "Troubleshooting"),
    ("about", "Settings and about"),
]

PLACEHOLDERS = [
    ("{stem}", "fCqk_000000", "the .tpx3 filename"),
    ("{measurement}", "Measurement_Aug_07_2026_12h52m45s", "measurement folder"),
    ("{campaign}", "data_DCR_07.08.2026", "the folder above that"),
    ("{date} {time} {datetime}", "2026-08-07, 12-52-45", "StartDateTime"),
    ("{duration}", "10s", "StopDateTime - StartDateTime"),
    ("{comment}", "DCR-0V-gain", "CommentAtTimeOfMeasurement, or comment.txt"),
    ("{bias}", "50", "BiasVoltage"),
    ("{exposure} {ntrig} {frames} {period}", "0.01, 100, 100, 0.1",
     "ExposureTime, nTriggers, NumberOfFrames, TriggerPeriod"),
    ("{polarity} {trigmode}", "Positive, AUTOTRIGSTART_TIMERSTOP",
     "Polarity, TriggerMode"),
    ("{size} {chip} {chipboard}", "256x256, W0028_H11, 2000050",
     "detector layout and board info"),
    ("{thr_coarse} {thr_fine}", "6, 246",
     "threshold DACs — may not follow a threshold changed mid-session"),
]

PLOT_NOTES = {
    "hitmap": ("PixelHits x, y", "hits per pixel, including cluster spread"),
    "cmap": ("Clusters cx, cy", "each cluster counted once, at its centroid"),
    "tot": ("Clusters ctot", "peak-pixel ToT; 25 ns bins, log y"),
    "stot": ("Clusters sum_tot", "total ToT of the cluster — the "
             "deposited-charge proxy; ~300 bins snapped to 25 ns, log y"),
    "csize": ("Clusters size", "pixels per cluster, 0-40; anything above is "
              "counted in the title"),
    "tdc": ("Clusters ctoa - TDCEvents", "time since the reference edge, over "
            "one trigger period, log y"),
}

TROUBLE = [
    ("Status reads none, \"no WSL distribution installed\"",
     "Run <code>wsl --install -d Ubuntu</code> in PowerShell, then press "
     "<b>Check install</b>. No restart needed."),
    ("tpx3dump not found under the Luna folder",
     "Point at the install root or its <code>bin</code> folder, not at the .zip."),
    ("<code>index out of bounds: the len is 0</code> after "
     "<code>Skipping file ...</code>",
     "WSL cannot see the drive the data is on — normal for USB sticks. "
     "Answer <b>Yes</b> when the GUI offers to mount it."),
    ("UNC path rejected", "Map <code>\\\\server\\share</code> to a drive letter first."),
    ("Files report <i>skipped - output exists</i>",
     "That is <b>Skip files whose output already exists</b>. Tick "
     "<b>Overwrite</b> on the rows to redo, or untick the option."),
    ("A run refuses to start with a flag error",
     "A value tpx3dump would reject, e.g. <code>--eps-t 100</code> without a "
     "unit. The message names the flag; fix it on the Advanced tab."),
    ("Inspect tab does nothing",
     "Install the analysis packages: <code>pip install h5py numpy pandas "
     "matplotlib</code>."),
    ("Inspect cannot read a file written with Blosc compression",
     "h5py needs <code>pip install hdf5plugin</code> for Blosc. Deflate needs "
     "nothing extra."),
    ("\"No /TDCEvents in this file\"",
     "The file predates tpx3dump's TDC support, or the run recorded no TDC. "
     "Reprocess the .tpx3."),
    ("Most rows report no TDC edge",
     "They come before the first reference edge — normal at the start of a run."),
    ("Batch is slow on Windows",
     "/mnt/d goes through WSL's file bridge; for big jobs copy the raw data "
     "into the WSL filesystem."),
]


def _table(rows, head, pal, widths=()):
    """A simple striped table; cells are HTML already."""
    out = ['<table width="100%" cellspacing="0" cellpadding="5">', "<tr>"]
    for i, h in enumerate(head):
        w = f' width="{widths[i]}"' if i < len(widths) else ""
        out.append(f'<th align="left"{w} bgcolor="{pal["surface_container_high"]}">'
                   f"{h}</th>")
    out.append("</tr>")
    for n, cells in enumerate(rows):
        bg = pal["surface_container"] if n % 2 else pal["surface_container_low"]
        out.append(f'<tr bgcolor="{bg}">'
                   + "".join(f'<td valign="top">{c}</td>' for c in cells)
                   + "</tr>")
    out.append("</table>")
    return "".join(out)


def _prose(text):
    """Escape for HTML, with the code's " -- " set as a proper dash."""
    return escape(text).replace(" -- ", " — ")


def _flags_html(pal):
    parts = []
    for title, group in FLAG_GROUPS:
        rows = []
        for f in group:
            what = _prose(f.note[0].upper() + f.note[1:]) + "."
            if f.tip:
                what += f'<br><span class="faint">{_prose(f.tip)}</span>'
            if f.choices and f.kind == "choice":
                what += ('<br><span class="faint">Values: '
                         + ", ".join(f"<code>{escape(c)}</code>" for c in f.choices)
                         + "</span>")
            rows.append([f"<code>{escape(f.flag)}</code>",
                         f"<code>{escape(f.default)}</code>" if f.default else "",
                         what])
        parts.append(f"<h3>{escape(title)}</h3>"
                     + _table(rows, ["Flag", "Default", "What it does"], pal,
                              ("32%", "12%")))
    return "".join(parts)


def help_html(pal) -> str:
    """The whole help page as HTML, coloured for palette `pal`."""
    flag_count = sum(len(g) for _t, g in FLAG_GROUPS)
    ph = _table([[f"<code>{escape(p)}</code>", escape(e), escape(s)]
                 for p, e, s in PLACEHOLDERS],
                ["Placeholder", "Example", "From"], pal, ("30%", "32%"))
    plots = _table([[f"<b>{escape(PLOT_TITLES[k])}</b>", escape(src), escape(what)]
                    for k, (src, what) in PLOT_NOTES.items()],
                   ["Plot", "Reads", "Shows"], pal, ("24%", "26%"))
    units = _table([[f"<code>{escape(k)}</code>", escape(v)]
                    for k, v in FIELD_UNITS.items()],
                   ["Column", "Meaning / unit"], pal, ("24%",))
    trouble = _table([[s, fix] for s, fix in TROUBLE],
                     ["Symptom", "Cause and fix"], pal, ("38%",))

    return f"""
<a name="start"></a><h2 class="first">Getting started</h2>
<p>The GUI runs your own Luna <code>tpx3dump</code> over a batch of
<code>.tpx3</code> files and writes one <code>.hdf5</code> per file. Luna is not
included; you point the GUI at your installation once. On Windows it runs the
Linux build of <code>tpx3dump</code> through WSL.</p>
<ol>
<li><b>Advanced</b> → <b>Luna installation</b> → <b>Browse...</b> to the folder
containing <code>bin/tpx3dump</code> → <b>Check install</b>. A one-time step.</li>
<li><b>Process</b> → <b>Add folders...</b> → <b>Run queue</b>.</li>
<li>Double-click a finished row to open its <code>.hdf5</code> on
<b>Inspect HDF5</b>.</li>
</ol>
<p>Left alone, every queued file is processed with exactly</p>
<pre>tpx3dump process -i NAME.tpx3 -o NAME.hdf5</pre>
<p>with the output written beside the input. Anything else you set turns the
<b>Advanced flags</b> button on the Process tab yellow, so a non-default run is
never a surprise. Your
<code>.tpx3</code> files are never moved, renamed or modified.</p>
<h3>Paths, the Explorer way</h3>
<ul>
<li>On Windows every <b>Browse...</b> opens Explorer's own dialog: Alt+D jumps
to its address bar, paste a path there, Ctrl+A selects all, Quick Access and
recent folders are all there.</li>
<li>Every path field takes a pasted path; the quotes Explorer's <i>Copy as
path</i> adds are dropped. A file or folder dragged in from Explorer lands as
its path.</li>
<li>On Inspect HDF5, paste or drop a file into <b>HDF5 file</b> and it opens
(Enter opens a typed path).</li>
</ul>

<a name="process"></a><h2>Process tab</h2>
<p>The everyday job: add input, press Run, watch the log.</p>
<ul>
<li><b>Status line</b>: whether <code>tpx3dump</code> can run here, and how
(native or WSL). <b>Set up Luna...</b> appears until it can.</li>
<li><b>Advanced flags</b>: grey while every file runs as the plain command,
yellow with a count as soon as anything differs: output placement, renaming,
overwriting, each flag passed. Click it for the full list, one setting per
row.</li>
<li><b>Add folders...</b> queues every <code>.tpx3</code> under one or more folders;
<b>Search subfolders</b> reaches the files inside each measurement's
<code>raw</code> folder. <b>Browse...</b> opens Explorer's own folder picker
(Alt+D for its address bar). Or paste several paths, one per line, or drag
folders in from Explorer; <i>Copy as path</i> works as-is.</li>
<li><b>Rescan</b>: re-reads the batch folders: queues new files, drops rows
whose input has gone, re-reads the metadata. During a live campaign,
<i>Rescan, Run, repeat</i> is the whole routine. Only run a measurement once it
has finished.</li>
<li><b>Clear</b> empties the queue and the folder list.</li>
<li><b>Folders to process</b>: the batch folders with their file counts,
remembered between sessions.</li>
<li><b>Files found</b>: each input with the output it will get and its status
(<i>queued, running, done, failed, skipped, CLASH</i>). Tick <b>Overwrite</b> on
a row to redo a file whose output exists; the box in the column header ticks
them all. Double-click a row to inspect its output.</li>
<li><b>Run queue</b> processes the files one at a time; <b>Stop</b> ends the
current file and the rest. The log shows <code>tpx3dump</code>'s own output.</li>
</ul>
<p>On Windows, before a run the GUI checks that WSL can see the drives
involved, and offers to mount one that it cannot (typically a USB disk).</p>

<a name="advanced"></a><h2>Advanced tab</h2>
<p>Everything here is optional.</p>
<h3>Luna installation</h3>
<p><b>Folder</b> is the Luna install root or its <code>bin</code> folder.
<b>Check install</b> re-detects the backend and prints
<code>tpx3dump --version</code> and <code>tpx3dump process --help</code> into
the log — the authoritative flag list for your Luna version.</p>
<h3>Output</h3>
<ul>
<li><b>Next to the input file</b> (default) — each <code>.hdf5</code> beside
its <code>.tpx3</code>.</li>
<li><b>Output folder (flat)</b>: every <code>.hdf5</code> in one folder.</li>
<li><b>Output folder (mirror tree)</b>: the campaign's folder structure
rebuilt under the output folder, without the <code>raw</code> level.</li>
<li><b>Name template</b>: how outputs are named; see
<a href="#naming">Name templates</a>. <b>Presets...</b> offers common ones.</li>
<li><b>Skip files whose output already exists</b> (on by default) — untick to
overwrite everything, or tick <b>Overwrite</b> on single rows instead.</li>
</ul>
<h3>tpx3dump flags</h3>
<p>All {flag_count} options of <code>tpx3dump process</code>, with a note on
each; see <a href="#flags">tpx3dump flags</a>. Blank means
<code>tpx3dump</code>'s own default. <b>extra arguments</b> is passed verbatim
after them, for anything a newer Luna adds.</p>
<h3>After processing</h3>
<p><b>Add TDC columns to each output .hdf5</b>: once <code>tpx3dump</code>
finishes a file, this GUI tags every hit and cluster with the TDC edge it
follows; see <a href="#tdc">TDC</a>. Not a <code>tpx3dump</code> flag.</p>
<h3>Buttons</h3>
<ul>
<li><b>Preview commands</b>: prints the exact command for every queued file,
without running anything.</li>
<li><b>Export .sh</b>: writes a shell script that runs the queue on a Linux
machine, with the input and output roots as variables to edit there.</li>
<li><b>Reset to defaults</b>: everything on this tab back to the plain run;
the Luna folder and the queue are kept.</li>
</ul>

<a name="naming"></a><h2>Name templates</h2>
<p>The default <code>{escape(DEFAULT_TEMPLATE)}</code> gives, for example,
<code>2026-08-07_12-52-45_DCR-0V-gain_fCqk_000000.hdf5</code>. The values come
from <code>measurement_metadata.json</code> and <code>comment.txt</code> in the
measurement folder.</p>
{ph}
<p>A placeholder with no value drops out and the separators collapse. If two
inputs would get the same name, both rows are marked <b>CLASH</b> and skipped
rather than one overwriting the other — keep <code>{{time}}</code> or
<code>{{stem}}</code> in the template to avoid it.</p>

<a name="flags"></a><h2>tpx3dump flags</h2>
<p>Taken from <code>tpx3dump process --help</code>. Blank fields pass nothing,
so <code>tpx3dump</code> uses the default shown. Times carry their unit
(<code>s ms us ns ps fs</code>): write <code>200ns</code>, not
<code>200</code>; a bare number is refused before anything runs.</p>
{_flags_html(pal)}

<a name="inspect"></a><h2>Inspect HDF5 tab</h2>
<p>Look inside a result. <b>Browse...</b> to a file, or <b>Use selected
output</b> for the row selected on the Process tab, then <b>Open</b>.</p>
<ul>
<li><b>Datasets</b>: every dataset with its shape, type, chunking and
compression.</li>
<li><b>View rows...</b>, or double-click a dataset — its rows in a window of
their own. It scrolls through the whole dataset, however large: only the rows
on screen are read. <b>Row</b>, <b>First</b> and <b>Last</b> jump anywhere; row
numbers count from 0, as h5py does. Hover a column header for its type and
unit; Ctrl+C copies the selected cells.</li>
<li><b>Summary</b> (bottom) — counts, fields, ToA and pixel ranges, whether
ToF was computed, mean cluster size, the TDC edges and their period.</li>
<li><b>TDC reference</b>: which edge starts the clock for the TDC columns and
the TDC plot; the same setting as on the Advanced tab.</li>
<li><b>Add TDC columns to this file</b>: writes them now, for this file.</li>
<li><b>Preview frame</b>: the first rows of the data joined with their TDC
columns.</li>
</ul>
<p>The six plots read the file in slices, so large files are fine, and each
opens in its own window for side-by-side comparison.</p>
{plots}

<a name="file"></a><h2>What is in the file</h2>
<ul>
<li><code>PixelHits</code>: one row per pixel hit.</li>
<li><code>Clusters</code>: one row per cluster of hits.</li>
<li><code>TDCEvents</code>: every TDC edge, repeated once per chip.</li>
<li><code>ExposureTimeBoundaries</code>: the frame boundaries of the
acquisition.</li>
<li><code>PixelHitsTDC</code>, <code>ClustersTDC</code>: the TDC columns, if
this GUI wrote them.</li>
</ul>
<p>All timestamps (<code>toa</code>, <code>ctoa</code>, TDC
<code>timestamp</code>) count 100 fs ticks of one clock, so subtracting them is
meaningful. ToT values are in ns, always multiples of 25 ns.</p>
{units}

<a name="tdc"></a><h2>TDC</h2>
<p><code>TDCEvents</code> holds every TDC edge <code>tpx3dump</code> saw:
<code>tdc_type</code> (1 TDC1Rising, 2 TDC1Falling, 3 TDC2Rising,
4 TDC2Falling), <code>trigger_count</code> and <code>timestamp</code>. Every
chip repeats the packet — a quad stores each edge four times — so everything
here deduplicates first; the summary shows both counts.</p>
<p><b>Add TDC columns</b> tags each hit and cluster with the last reference edge
before it and writes the result to <code>/PixelHitsTDC</code> and
<code>/ClustersTDC</code>, row-aligned with <code>PixelHits</code> and
<code>Clusters</code>: <code>tdc</code> (the edge's timestamp),
<code>tdc_dt</code> (time since it), <code>tdc_index</code>,
<code>tdc_trigger</code> and <code>tdc_type</code>. Rows before the first edge
get -1. The original datasets are never rewritten, and the GUI refuses to
replace TDC columns it did not write.</p>
<p>This is independent of <code>--tof-tdc-reference</code>, which makes
<code>tpx3dump</code> fill <code>PixelHits/tof</code> during processing. Where
both use the same edge they agree exactly; the TDC columns can be recomputed
against another edge without reprocessing the <code>.tpx3</code>. <b>Any
edge</b> tags from the latest edge of any type.</p>

<a name="trouble"></a><h2>Troubleshooting</h2>
{trouble}

<a name="about"></a><h2>Settings and about</h2>
<p>{escape(APP_NAME)}, version {escape(__version__)}. F1 opens this window
from anywhere in the app.</p>
<p>Settings — Luna folder, batch folders, template, flags, TDC reference and
theme — are saved on exit to <code>{escape(str(CONFIG_PATH))}</code>. The
<b>View</b> menu switches between the light and dark theme.</p>
<p>This program only wraps Luna: it runs your unmodified <code>tpx3dump</code>
through its command line and contains no part of it.</p>
"""


def style_sheet(pal, mono) -> str:
    """CSS for the rich text, which the app stylesheet does not reach."""
    # Sized and spaced for reading rather than scanning: 11 pt body with
    # open line spacing, section titles in the heading colour, bold terms
    # in the text colour so they stand out from the prose around them.
    return f"""
        body {{ color: {pal['text']}; font-size: 11pt; }}
        p {{ line-height: 135%; margin-top: 4px; margin-bottom: 8px; }}
        li {{ line-height: 135%; margin-bottom: 4px; }}
        ul, ol {{ margin-top: 2px; margin-bottom: 8px; }}
        h2 {{ font-size: 15pt; font-weight: 700; color: {pal['heading']};
              margin-top: 28px; margin-bottom: 6px; }}
        h2.first {{ margin-top: 0; }}
        h3 {{ font-size: 12pt; font-weight: 700; color: {pal['text']};
              margin-top: 18px; margin-bottom: 4px; }}
        b {{ color: {pal['text']}; font-weight: 700; }}
        a {{ color: {pal['heading']}; text-decoration: none; }}
        code {{ font-family: "{mono}"; font-size: 10pt; color: {pal['text']};
                background-color: {pal['surface_container_high']}; }}
        pre {{ font-family: "{mono}"; font-size: 10pt;
               background-color: {pal['surface_container_high']}; }}
        th {{ color: {pal['text_muted']}; font-weight: 700; }}
        td {{ line-height: 130%; }}
        .muted {{ color: {pal['text_muted']}; }}
        .faint {{ color: {pal['text_faint']}; font-size: 10pt; }}
    """


class HelpWindow(QDialog):
    """Topic list on the left, the page on the right, a find box on top."""

    def __init__(self, pal, mono, parent=None):
        super().__init__(parent)
        self.setWindowTitle(APP_NAME + " — Help")
        self.resize(980, 720)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(12, 12, 12, 12)
        lay.setSpacing(8)

        self.e_find = QLineEdit()
        self.e_find.setPlaceholderText("Search the guide... (Enter for next)")
        self.e_find.setClearButtonEnabled(True)
        self.e_find.returnPressed.connect(self.find_next)
        self.lbl_find = QLabel("")
        self.lbl_find.setProperty("faint", True)
        lay.addWidget(row("Find:", self.e_find, self.lbl_find))

        body = QHBoxLayout()
        body.setSpacing(8)
        self.nav = QListWidget()
        self.nav.setProperty("nav", True)
        self.nav.addItems([title for _a, title in SECTIONS])
        self.nav.setFixedWidth(210)
        self.nav.currentRowChanged.connect(
            lambda r: r >= 0 and self.view.scrollToAnchor(SECTIONS[r][0]))
        body.addWidget(self.nav)

        self.view = QTextBrowser()
        # The text wraps to the width, so a horizontal bar is only ever the
        # few pixels the vertical bar takes when it appears.
        self.view.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        # Links are handled here: #anchors scroll the page and select the
        # topic, web links go to the browser.
        self.view.setOpenLinks(False)
        self.view.anchorClicked.connect(self._link)
        body.addWidget(self.view, 1)
        lay.addLayout(body, 1)

        self.mono = mono
        self.set_palette(pal)

    def set_palette(self, pal):
        """Re-render in new colours, keeping the reader's place."""
        bar = self.view.verticalScrollBar()
        pos = bar.value()
        self.view.document().setDefaultStyleSheet(style_sheet(pal, self.mono))
        self.view.setHtml(help_html(pal))
        bar.setValue(pos)

    def show_section(self, anchor):
        for r, (a, _t) in enumerate(SECTIONS):
            if a == anchor:
                self.nav.setCurrentRow(r)
                self.view.scrollToAnchor(anchor)

    def _link(self, url):
        if url.scheme() in ("http", "https"):
            QDesktopServices.openUrl(url)
        elif url.fragment():
            self.show_section(url.fragment())

    def find_next(self):
        text = self.e_find.text().strip()
        if not text:
            return
        if not self.view.find(text):
            # Wrap around: back to the top and try once more.
            cur = self.view.textCursor()
            cur.movePosition(cur.MoveOperation.Start)
            self.view.setTextCursor(cur)
            if not self.view.find(text):
                self.lbl_find.setText("not found")
                return
            self.lbl_find.setText("wrapped to the top")
            return
        self.lbl_find.setText("")

