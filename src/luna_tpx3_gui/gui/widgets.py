"""Small widget helpers and the queue's check-box header."""

from __future__ import annotations

from PySide6.QtCore import QRect, QRectF, Qt, Signal
from PySide6.QtGui import QColor, QPainterPath, QPen
from PySide6.QtWidgets import (QAbstractItemView, QFrame, QHBoxLayout,
                               QHeaderView, QLabel, QPushButton, QTableView,
                               QWidget)

# ---------------------------------------------------------------------------
# small widget helpers
# ---------------------------------------------------------------------------

def vline():
    f = QFrame()
    f.setProperty("vline", True)
    f.setFixedWidth(1)
    return f


def hline():
    f = QFrame()
    f.setProperty("hline", True)
    f.setFrameShape(QFrame.Shape.HLine)
    return f


def row(*widgets, spacing=6, margins=(0, 0, 0, 0)):
    """A QWidget holding a horizontal row; None means 'stretch here'."""
    w = QWidget()
    lay = QHBoxLayout(w)
    lay.setContentsMargins(*margins)
    lay.setSpacing(spacing)
    for item in widgets:
        if item is None:
            lay.addStretch(1)
        elif isinstance(item, str):
            lay.addWidget(QLabel(item))
        else:
            lay.addWidget(item)
    return w


def button(text, slot=None, accent=False, toggle=False, danger=False, tip=""):
    b = QPushButton(text)
    if accent:
        b.setProperty("accent", True)
    if danger:
        b.setProperty("danger", True)
    if toggle:
        b.setProperty("toggle", True)
        b.setCheckable(True)
    if slot:
        b.clicked.connect(slot)
    if tip:
        b.setToolTip(tip)
    return b


class CheckHeader(QHeaderView):
    """Horizontal header that draws a master checkbox in one section.

    The box is painted by hand rather than through PE_IndicatorCheckBox: under
    a stylesheet the QCheckBox::indicator rules only reach real QCheckBoxes, so
    a style-drawn indicator here would ignore the theme. Same shape, same
    colours, drawn from the same palette.

    Clicking anywhere on the section emits box_clicked; the owner decides what
    "tick everything" means and pushes the result back through set_state(), so
    the header never second-guesses the model.
    """

    box_clicked = Signal()
    BOX = 15                            # matches QCheckBox::indicator in the QSS

    def __init__(self, column, palette, label="", parent=None):
        super().__init__(Qt.Orientation.Horizontal, parent)
        self.box_col = column
        self.pal = palette
        self.label = label
        self.box_state = Qt.CheckState.Unchecked
        self.setSectionsClickable(True)
        self.sectionClicked.connect(self._clicked)

    def _clicked(self, index):
        if index == self.box_col:
            self.box_clicked.emit()

    def set_palette(self, palette):
        self.pal = palette
        self.updateSection(self.box_col)

    def set_state(self, state):
        if state != self.box_state:
            self.box_state = state
            self.updateSection(self.box_col)

    def paintSection(self, painter, rect, index):
        # The model reports an empty title for this section, so the base class
        # paints the themed background and nothing else; the box and the label
        # go on top of it here.
        #
        # save()/restore() around the base call is not optional: it leaves the
        # painter with an empty clip region, and anything drawn afterwards is
        # silently clipped away.
        painter.save()
        super().paintSection(painter, rect, index)
        painter.restore()
        if index != self.box_col:
            return
        checked = self.box_state == Qt.CheckState.Checked
        partial = self.box_state == Qt.CheckState.PartiallyChecked
        box = QRectF(rect.x() + 8.5,
                     rect.y() + (rect.height() - self.BOX) / 2.0 + 0.5,
                     self.BOX - 1, self.BOX - 1)

        painter.save()
        painter.setRenderHint(painter.RenderHint.Antialiasing, True)
        fill = self.pal["primary"] if checked or partial else             self.pal["surface_container_low"]
        edge = self.pal["primary_border"] if checked or partial else             self.pal["outline"]
        painter.setPen(QPen(QColor(edge), 1))
        painter.setBrush(QColor(fill))
        painter.drawRoundedRect(box, 4, 4)

        mark = QPen(QColor(self.pal["on_primary"]), 2,
                    Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap,
                    Qt.PenJoinStyle.RoundJoin)
        if checked:
            path = QPainterPath()
            path.moveTo(box.x() + box.width() * 0.24, box.y() + box.height() * 0.52)
            path.lineTo(box.x() + box.width() * 0.44, box.y() + box.height() * 0.72)
            path.lineTo(box.x() + box.width() * 0.78, box.y() + box.height() * 0.28)
            painter.setPen(mark)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawPath(path)
        elif partial:
            painter.setPen(mark)
            painter.drawLine(int(box.x() + box.width() * 0.25),
                             int(box.center().y()),
                             int(box.x() + box.width() * 0.75),
                             int(box.center().y()))

        if self.label:
            painter.setPen(QColor(self.pal["text_muted"]))
            text = QRect(int(box.right()) + 7, rect.y(),
                         rect.right() - int(box.right()) - 11, rect.height())
            painter.drawText(text, int(Qt.AlignmentFlag.AlignLeft |
                                       Qt.AlignmentFlag.AlignVCenter),
                             painter.fontMetrics().elidedText(
                                 self.label, Qt.TextElideMode.ElideRight,
                                 text.width()))
        painter.restore()


def table(model, stretch_cols=(), widths=()):
    v = QTableView()
    v.setModel(model)
    v.setAlternatingRowColors(True)
    v.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
    v.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
    v.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
    v.verticalHeader().setVisible(False)
    v.verticalHeader().setDefaultSectionSize(24)
    v.setShowGrid(False)
    hdr = v.horizontalHeader()
    hdr.setHighlightSections(False)
    hdr.setDefaultAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
    for i, w in enumerate(widths):
        v.setColumnWidth(i, w)
    for i in range(model.columnCount()):
        hdr.setSectionResizeMode(
            i, QHeaderView.ResizeMode.Stretch if i in stretch_cols
            else QHeaderView.ResizeMode.Interactive)
    return v
