"""Table models behind the queue ("Files found") and the batch folder list."""

from __future__ import annotations

from PySide6.QtCore import QAbstractTableModel, QModelIndex, Qt
from PySide6.QtGui import QColor

from ..functions.common import human_size

# ---------------------------------------------------------------------------
# table models
# ---------------------------------------------------------------------------

STATUS_COLOUR = {
    "done": "success", "failed": "error", "CLASH": "error",
    "skipped": "warning", "running": "info",
}


class JobModel(QAbstractTableModel):
    HEADERS = ("Status", "Input file", "Size", "Output file", "Overwrite",
               "Measurement folder")
    OVER = 4                  # the Overwrite column

    def __init__(self, window):
        super().__init__()
        self.w = window

    @property
    def jobs(self):
        return self.w.jobs

    def rowCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else len(self.jobs)

    def columnCount(self, parent=QModelIndex()):
        return len(self.HEADERS)

    def headerData(self, section, orientation, role=Qt.ItemDataRole.DisplayRole):
        if role == Qt.ItemDataRole.DisplayRole and orientation == Qt.Orientation.Horizontal:
            # CheckHeader paints this one itself, box first, label after.
            return "" if section == self.OVER else self.HEADERS[section]
        if role == Qt.ItemDataRole.ToolTipRole and section == self.OVER:
            return ("Tick a file to rewrite its .hdf5 even though it is "
                    "already there.\nThe box in this header ticks or clears "
                    "every file that has one.")
        return None

    def data(self, index, role=Qt.ItemDataRole.DisplayRole):
        if not index.isValid():
            return None
        job = self.jobs[index.row()]
        col = index.column()
        if role == Qt.ItemDataRole.DisplayRole:
            if col == 0:
                return job.status + (" - " + job.note if job.note else "")
            if col == 1:
                return job.src.name
            if col == 2:
                try:
                    return human_size(job.src.stat().st_size)
                except Exception:
                    return "?"
            if col == 3:
                return job.dst.name if job.dst else ""
            if col == self.OVER:
                return ""      # the checkbox is the whole content of this cell
            return (job.ctx.get("campaign", "") + " / " + job.ctx.get("measurement", ""))
        if role == Qt.ItemDataRole.CheckStateRole and col == self.OVER:
            # Only offer a box where there is actually something to clobber.
            if not self.w.job_clobbers(job):
                return None
            return (Qt.CheckState.Checked if job.overwrite
                    else Qt.CheckState.Unchecked)
        if role == Qt.ItemDataRole.ForegroundRole:
            key = STATUS_COLOUR.get(job.status)
            if key:
                return QColor(self.w.pal[key])
        if role == Qt.ItemDataRole.ToolTipRole:
            if col == self.OVER:
                if not self.w.job_clobbers(job):
                    return "No output file exists yet - nothing to overwrite."
                return ("This .hdf5 already exists.\n"
                        "Tick to rewrite it, leave it clear to skip this file.")
            return f"in:  {job.src}\nout: {job.dst}"
        return None

    def flags(self, index):
        f = super().flags(index)
        if (index.column() == self.OVER
                and self.w.job_clobbers(self.jobs[index.row()])):
            f |= Qt.ItemFlag.ItemIsUserCheckable
        return f

    def setData(self, index, value, role=Qt.ItemDataRole.EditRole):
        if role != Qt.ItemDataRole.CheckStateRole or index.column() != self.OVER:
            return False
        job = self.jobs[index.row()]
        job.overwrite = Qt.CheckState(value) == Qt.CheckState.Checked
        self.dataChanged.emit(index, index, [role])
        self.w.sync_overwrite_header()
        return True

    def overwrite_column_changed(self):
        if self.jobs:
            self.dataChanged.emit(self.index(0, self.OVER),
                                  self.index(len(self.jobs) - 1, self.OVER))

    def reset(self):
        self.beginResetModel()
        self.endResetModel()

    def row_changed(self, row):
        if 0 <= row < len(self.jobs):
            self.dataChanged.emit(self.index(row, 0),
                                  self.index(row, self.columnCount() - 1))


class FolderModel(QAbstractTableModel):
    HEADERS = ("Folder", ".tpx3", "Subdirs")

    def __init__(self, window):
        super().__init__()
        self.w = window

    @property
    def folders(self):
        return self.w.folders

    def rowCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else len(self.folders)

    def columnCount(self, parent=QModelIndex()):
        return len(self.HEADERS)

    def headerData(self, section, orientation, role=Qt.ItemDataRole.DisplayRole):
        if role == Qt.ItemDataRole.DisplayRole and orientation == Qt.Orientation.Horizontal:
            return self.HEADERS[section]
        return None

    def data(self, index, role=Qt.ItemDataRole.DisplayRole):
        if not index.isValid():
            return None
        entry = self.folders[index.row()]
        n = entry["count"]
        if role == Qt.ItemDataRole.DisplayRole:
            if index.column() == 0:
                return entry["path"]
            if index.column() == 1:
                return {None: "...", -1: "missing", 0: "0"}.get(n, str(n))
            return "yes" if entry["recursive"] else "no"
        if role == Qt.ItemDataRole.ForegroundRole:
            if n == -1:
                return QColor(self.w.pal["error"])
            if n == 0:
                return QColor(self.w.pal["warning"])
        if role == Qt.ItemDataRole.ToolTipRole:
            return entry["path"]
        return None

    def reset(self):
        self.beginResetModel()
        self.endResetModel()
