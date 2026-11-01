"""A scrollable window onto one HDF5 dataset, however many rows it has.

Nothing is read up front but the shape and dtype. The table itself only ever
holds the rows that fit on screen; a separate scroll bar spans the whole
dataset and slides that window along it. Qt's own scrolling cannot do this:
its row header keeps an entry per row, which for a few hundred million hits
is gigabytes and minutes before the first paint.

Rows are read a block at a time, aligned with the file's chunks, so h5py
decompresses only what is shown and a 5 GB file opens as fast as a small one.
The file is opened per block and closed straight after, so the viewer never
holds a handle that would stop "Add TDC columns" or tpx3dump from writing to
the same file on Windows.
"""

from __future__ import annotations

from collections import OrderedDict
from pathlib import Path

from PySide6.QtCore import QAbstractTableModel, QEvent, QModelIndex, Qt, Signal
from PySide6.QtGui import QFont, QKeySequence, QShortcut
from PySide6.QtWidgets import (QAbstractItemView, QApplication, QDialog,
                               QHBoxLayout, QHeaderView, QLabel, QScrollBar,
                               QSpinBox, QTableView, QVBoxLayout)

from .widgets import button, row

# What the numbers mean, for the column header tooltips. Only fields whose
# unit this project has checked against real files are listed.
FIELD_UNITS = {
    "toa": "100 fs ticks",
    "ctoa": "100 fs ticks",
    "timestamp": "100 fs ticks",
    "tof": "100 fs ticks since the --tof-tdc-reference edge; -1 = unset",
    "tdc": "100 fs ticks, timestamp of the reference edge",
    "tdc_dt": "100 fs ticks since the reference edge; -1 = no edge yet",
    "tot": "ns, in steps of 25 ns",
    "ctot": "ns, the cluster's peak-pixel ToT",
    "sum_tot": "ns, the cluster's total ToT",
    "x": "pixel column", "y": "pixel row",
    "cx": "pixel column", "cy": "pixel row",
    "size": "pixels in the cluster",
    "tdc_type": "1 TDC1Rising, 2 TDC1Falling, 3 TDC2Rising, 4 TDC2Falling",
}

# The scroll bar counts rows in an int.
MAX_ROWS = 2**31 - 1
ROW_HEIGHT = 22
WHEEL_ROWS = 3


class DatasetModel(QAbstractTableModel):
    """The on-screen slice of one dataset: rows top .. top + count."""

    read_failed = Signal(str)
    CACHED_BLOCKS = 8

    def __init__(self, path, name, h5py, np, parent=None):
        super().__init__(parent)
        self.path, self.name, self.h5py, self.np = str(path), name, h5py, np
        with h5py.File(self.path, "r") as f:
            ds = f[name]
            self.shape, self.dtype = ds.shape, ds.dtype
            # One block per chunk where the file has chunks: a read then
            # decompresses exactly the chunks it shows.
            self.block = min(max(ds.chunks[0] if ds.chunks else 10000, 1000),
                             100000)
        if self.dtype.names:
            self.columns = list(self.dtype.names)
        elif len(self.shape) <= 1:
            self.columns = ["value"]
        elif len(self.shape) == 2:
            self.columns = [str(i) for i in range(self.shape[1])]
        else:
            raise ValueError(f"/{name} has {len(self.shape)} dimensions; "
                             "only tables (1-D or 2-D) can be shown.")
        self.n = self.shape[0] if self.shape else 1
        self.shown = min(self.n, MAX_ROWS)
        self.top = self.count = 0
        self.cache = OrderedDict()
        self.failed = False

    # -- the window -------------------------------------------------------

    def set_window(self, top, count):
        """Show `count` rows from `top`, both clamped to the dataset."""
        count = max(0, min(count, self.shown))
        top = max(0, min(top, self.shown - count))
        if count > self.count:
            self.beginInsertRows(QModelIndex(), self.count, count - 1)
            self.count = count
            self.endInsertRows()
        elif count < self.count:
            self.beginRemoveRows(QModelIndex(), count, self.count - 1)
            self.count = count
            self.endRemoveRows()
        if top != self.top:
            self.top = top
            if count:
                self.dataChanged.emit(self.index(0, 0),
                                      self.index(count - 1, len(self.columns) - 1))
                self.headerDataChanged.emit(Qt.Orientation.Vertical, 0, count - 1)

    def rowCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else self.count

    def columnCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else len(self.columns)

    # -- reading ----------------------------------------------------------

    def _rows(self, b):
        """Block b of the dataset, read on first use, None if unreadable."""
        if b in self.cache:
            self.cache.move_to_end(b)
            return self.cache[b]
        try:
            with self.h5py.File(self.path, "r") as f:
                ds = f[self.name]
                arr = (self.np.atleast_1d(ds[()]) if not self.shape
                       else ds[b * self.block:(b + 1) * self.block])
        except Exception as exc:
            if not self.failed:
                self.failed = True
                self.read_failed.emit(f"Could not read /{self.name}: {exc}")
            return None
        self.cache[b] = arr
        if len(self.cache) > self.CACHED_BLOCKS:
            self.cache.popitem(last=False)
        return arr

    def text(self, r, c):
        """Cell (r, c) as display text; r counts from the dataset's start."""
        b, i = divmod(r, self.block)
        arr = self._rows(b)
        if arr is None:
            return "?"
        rec = arr[i]
        if self.dtype.names:
            v = rec[self.columns[c]]
        else:
            v = rec if rec.ndim == 0 else rec[c]
        if isinstance(v, bytes):
            return v.decode(errors="replace")
        if getattr(v, "ndim", 0):
            return str(v.tolist())
        if getattr(v, "dtype", None) is not None and v.dtype.kind == "f":
            return f"{v:.6g}"
        return str(v)

    def data(self, index, role=Qt.ItemDataRole.DisplayRole):
        if not index.isValid():
            return None
        if role == Qt.ItemDataRole.DisplayRole:
            return self.text(self.top + index.row(), index.column())
        if role == Qt.ItemDataRole.TextAlignmentRole:
            return int(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        return None

    def headerData(self, section, orientation, role=Qt.ItemDataRole.DisplayRole):
        if orientation == Qt.Orientation.Vertical:
            # Row numbers from 0, as h5py and numpy index them.
            if role == Qt.ItemDataRole.DisplayRole:
                return f"{self.top + section:,}"
            if role == Qt.ItemDataRole.TextAlignmentRole:
                return int(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            return None
        col = self.columns[section]
        if role == Qt.ItemDataRole.DisplayRole:
            return col
        if role == Qt.ItemDataRole.ToolTipRole:
            dt = self.dtype[col] if self.dtype.names else self.dtype
            unit = FIELD_UNITS.get(col)
            return str(dt) + ("\n" + unit if unit else "")
        return None


class DatasetViewer(QDialog):
    """The window: info line, the table with its own scroll bar, navigation."""

    def __init__(self, path, name, h5py, np, mono, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        self.setWindowTitle(f"/{name} -- {Path(path).name}")
        self.resize(940, 600)
        m = self.model = DatasetModel(path, name, h5py, np, self)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(12, 12, 12, 10)
        lay.setSpacing(8)

        info = QLabel(f"/{name}    {m.n:,} rows    {len(m.columns)} columns    "
                      f"read {m.block:,} rows at a time")
        info.setProperty("muted", True)
        lay.addWidget(info)
        hint = QLabel("Values as stored in the file. Hover a column header "
                      "for its type and unit; Ctrl+C copies the selected cells.")
        hint.setProperty("faint", True)
        lay.addWidget(hint)
        if m.n > MAX_ROWS:
            over = QLabel(f"Only the first {MAX_ROWS:,} rows can be shown.")
            over.setProperty("role", "warn")
            lay.addWidget(over)
        self.err = QLabel("")
        self.err.setProperty("role", "error")
        self.err.setWordWrap(True)
        self.err.hide()
        lay.addWidget(self.err)
        m.read_failed.connect(self._show_error)

        v = self.view = QTableView()
        v.setModel(m)
        v.setFont(QFont(mono))
        v.setAlternatingRowColors(True)
        v.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        v.setShowGrid(False)
        v.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        vh = v.verticalHeader()
        vh.setSectionResizeMode(QHeaderView.ResizeMode.Fixed)
        vh.setDefaultSectionSize(ROW_HEIGHT)
        # Wide enough for the last row's number up front, so the header does
        # not jump as the numbers grow.
        vh.setMinimumWidth(vh.fontMetrics().horizontalAdvance(f"{m.shown:,}") + 24)
        hh = v.horizontalHeader()
        hh.setDefaultAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)

        self.sb = QScrollBar(Qt.Orientation.Vertical)
        self.sb.valueChanged.connect(self._scrolled)
        self._keep_selection = False
        box = QHBoxLayout()
        box.setSpacing(2)
        box.addWidget(v, 1)
        box.addWidget(self.sb)
        lay.addLayout(box, 1)

        # Size the columns from the first and the last rows -- times only grow
        # down a sorted file -- then hand over to the viewport's resize events.
        widths = [90] * m.columnCount()
        for top in (m.shown, 0):
            m.set_window(top, 30)
            v.resizeColumnsToContents()
            widths = [max(w, v.columnWidth(c)) for c, w in enumerate(widths)]
        for c, w in enumerate(widths):
            v.setColumnWidth(c, w)
        v.viewport().installEventFilter(self)
        v.installEventFilter(self)
        QShortcut(QKeySequence.StandardKey.Copy, v, self.copy_selection)

        self.sp_row = QSpinBox()
        self.sp_row.setRange(0, max(m.shown - 1, 0))
        self.sp_row.setGroupSeparatorShown(True)
        self.sp_row.setMinimumWidth(140)
        self.sp_row.lineEdit().returnPressed.connect(self.go)
        lay.addWidget(row(
            QLabel("Row:"), self.sp_row, button("Go", self.go),
            button("First", lambda: self.go(0)),
            button("Last", lambda: self.go(m.shown - 1)),
            None, button("Close", self.close)))

    # -- scrolling --------------------------------------------------------

    def _fit_window(self):
        """Match the window to however many rows the viewport now holds."""
        count = max(1, self.view.viewport().height() // ROW_HEIGHT)
        self.sb.setRange(0, max(self.model.shown - count, 0))
        self.sb.setPageStep(count)
        self.model.set_window(self.sb.value(), count)

    def _scrolled(self, top):
        # The selection belongs to screen rows, not to data: after a scroll it
        # would sit on different values, so drop it -- unless the arrow keys
        # are walking it past the edge, where staying put is the point.
        if not self._keep_selection:
            self.view.clearSelection()
        self.model.set_window(top, self.model.count)

    def eventFilter(self, obj, ev):
        if obj is self.view.viewport():
            if ev.type() == QEvent.Type.Resize:
                self._fit_window()
            elif ev.type() == QEvent.Type.Wheel and ev.angleDelta().y():
                self.sb.setValue(self.sb.value()
                                 - ev.angleDelta().y() * WHEEL_ROWS // 120)
                return True
        elif obj is self.view and ev.type() == QEvent.Type.KeyPress:
            return self._key(ev)
        return super().eventFilter(obj, ev)

    def _key(self, ev):
        """Arrow keys and paging that run past the screen move the window."""
        key, cur = ev.key(), self.view.currentIndex().row()
        last = self.model.count - 1
        ctrl = ev.modifiers() & Qt.KeyboardModifier.ControlModifier
        step = {Qt.Key.Key_PageDown: self.sb.pageStep(),
                Qt.Key.Key_PageUp: -self.sb.pageStep()}.get(key, 0)
        if key == Qt.Key.Key_Down and cur == last:
            step = 1
        elif key == Qt.Key.Key_Up and cur == 0:
            step = -1
        elif ctrl and key == Qt.Key.Key_Home:
            self.go(0)
            return True
        elif ctrl and key == Qt.Key.Key_End:
            self.go(self.model.shown - 1)
            return True
        if not step:
            return False
        self._keep_selection = True
        self.sb.setValue(self.sb.value() + step)
        self._keep_selection = False
        return True

    def go(self, r=None):
        """Bring dataset row r to the top of the screen and select it."""
        r = self.sp_row.value() if r is None or r is False else r
        self.sp_row.setValue(r)
        self.sb.setValue(r)
        self.view.selectRow(r - self.model.top)

    def _show_error(self, text):
        self.err.setText(text)
        self.err.show()

    def copy_selection(self):
        """Selected cells as tab-separated text, header line first."""
        idx = self.view.selectionModel().selectedIndexes()
        if not idx:
            return
        top = self.model.top
        rows = sorted({i.row() for i in idx})
        cols = sorted({i.column() for i in idx})
        picked = {(i.row(), i.column()) for i in idx}
        lines = ["\t".join(self.model.columns[c] for c in cols)]
        for r in rows:
            lines.append("\t".join(self.model.text(top + r, c)
                                   if (r, c) in picked else "" for c in cols))
        QApplication.clipboard().setText("\n".join(lines))
