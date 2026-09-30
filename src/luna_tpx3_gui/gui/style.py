"""Appearance: the light and dark palettes and the stylesheet built from them."""

from __future__ import annotations

from PySide6.QtGui import QColor, QFontDatabase, QPalette

# ---------------------------------------------------------------------------
# appearance: two palettes, light and dark
# ---------------------------------------------------------------------------

PALETTES = {
    "light": dict(
        surface="#ffffff",
        surface_container_low="#f9fafb",
        surface_container="#f3f4f6",
        surface_container_high="#e5e7eb",
        surface_container_highest="#e5e7eb",
        primary="#007aff", primary_hover="#0062cc", primary_border="#005bb5",
        on_primary="#ffffff",
        outline="#9ca3af", outline_variant="#d1d5db",
        text="#111827", text_muted="#4b5563", text_faint="#6b7280",
        success="#1a7f37", warning="#8a6d00", error="#d32f2f", info="#0b5cad",
        alert_bg="#fef2f2", alert_border="#fecaca",
        tab_active_bg="#f9fafb", tab_active_fg="#111827",
        selection="#cfe4ff", grid="#e5e7eb",
    ),
    "dark": dict(
        surface="#131315",
        surface_container_low="#1b1b1d",
        surface_container="#202022",
        surface_container_high="#2a2a2c",
        surface_container_highest="#353537",
        primary="#007aff", primary_hover="#0a84ff", primary_border="#005bb5",
        on_primary="#ffffff",
        outline="#8e8e93", outline_variant="#48484a",
        text="#e5e5e5", text_muted="#9ca3af", text_faint="#8e8e93",
        success="#32d74b", warning="#ffd60a", error="#ff453a", info="#409cff",
        alert_bg="#202022", alert_border="#48484a",
        tab_active_bg="#353537", tab_active_fg="#ffffff",
        selection="#0a3a66", grid="#2a2a2c",
    ),
}

_FONT_SANS_CANDIDATES = ("Inter", "Segoe UI", "SF Pro Text", "Helvetica Neue",
                         "Noto Sans", "Helvetica", "Arial")
_FONT_MONO_CANDIDATES = ("Cascadia Mono", "Consolas", "SF Mono", "Menlo",
                         "DejaVu Sans Mono", "Courier New", "Courier")


def pick_font(candidates, fallback=""):
    try:
        available = set(QFontDatabase.families())
    except Exception:
        return fallback
    for name in candidates:
        if name in available:
            return name
    return fallback


def build_palette(pal: dict) -> QPalette:
    """A real QPalette to back the stylesheet.

    The stylesheet cannot reach everything -- non-native file dialogs, combo
    popups, tooltips, disabled text -- and whatever it misses would otherwise
    fall back to Fusion's built-in light colours, which looks broken in dark
    mode. Setting both keeps them consistent.
    """
    c = QColor
    p = QPalette()
    p.setColor(QPalette.ColorRole.Window, c(pal["surface"]))
    p.setColor(QPalette.ColorRole.WindowText, c(pal["text"]))
    p.setColor(QPalette.ColorRole.Base, c(pal["surface_container_low"]))
    p.setColor(QPalette.ColorRole.AlternateBase, c(pal["surface_container"]))
    p.setColor(QPalette.ColorRole.Text, c(pal["text"]))
    p.setColor(QPalette.ColorRole.Button, c(pal["surface_container"]))
    p.setColor(QPalette.ColorRole.ButtonText, c(pal["text"]))
    p.setColor(QPalette.ColorRole.Highlight, c(pal["primary"]))
    p.setColor(QPalette.ColorRole.HighlightedText, c(pal["on_primary"]))
    p.setColor(QPalette.ColorRole.ToolTipBase, c(pal["surface_container_highest"]))
    p.setColor(QPalette.ColorRole.ToolTipText, c(pal["text"]))
    p.setColor(QPalette.ColorRole.PlaceholderText, c(pal["text_faint"]))
    p.setColor(QPalette.ColorRole.Link, c(pal["primary"]))
    for role in (QPalette.ColorRole.Text, QPalette.ColorRole.ButtonText,
                 QPalette.ColorRole.WindowText):
        p.setColor(QPalette.ColorGroup.Disabled, role, c(pal["text_faint"]))
    return p


def build_qss(pal: dict, sans: str, mono: str) -> str:
    """One stylesheet for the whole app, generated from a palette."""
    return f"""
    * {{
        font-family: "{sans}";
        font-size: 10pt;
    }}
    /* Only real containers paint a background. A blanket QWidget rule would
       make every QLabel and QCheckBox paint the window colour on top of the
       group box it sits in, which shows as pale bands behind the text. */
    QMainWindow, QDialog {{ background: {pal['surface']}; }}
    QLabel, QCheckBox, QRadioButton, QFrame {{
        background: transparent;
        color: {pal['text']};
    }}
    QLabel[muted="true"]  {{ color: {pal['text_muted']}; }}
    QLabel[faint="true"]  {{ color: {pal['text_faint']}; font-size: 9pt; }}
    QLabel[role="ok"]     {{ color: {pal['success']}; }}
    QLabel[role="warn"]   {{ color: {pal['warning']}; }}
    QLabel[role="error"]  {{ color: {pal['error']}; }}
    QLabel[heading="true"] {{ font-size: 11pt; font-weight: 600; }}
    QLabel[intro="true"]  {{ font-size: 11pt; color: {pal['text']}; }}
    QLabel[code="true"] {{
        font-family: "{mono}";
        font-size: 11pt;
        color: {pal['text']};
        background: {pal['surface_container_high']};
        border: 1px solid {pal['outline_variant']};
        border-left: 3px solid {pal['primary']};
        border-radius: 6px;
        padding: 6px 14px;
    }}

    /* ---- tabs ---------------------------------------------------------- */
    QTabWidget::pane {{
        border: 1px solid {pal['outline_variant']};
        border-radius: 8px;
        top: -1px;
        background: {pal['surface']};
    }}
    QTabBar::tab {{
        background: transparent;
        color: {pal['text_muted']};
        padding: 8px 18px;
        margin-right: 2px;
        border: 1px solid transparent;
        border-top-left-radius: 8px;
        border-top-right-radius: 8px;
    }}
    QTabBar::tab:hover {{ color: {pal['text']}; }}
    QTabBar::tab:selected {{
        background: {pal['tab_active_bg']};
        color: {pal['tab_active_fg']};
        border-color: {pal['outline_variant']};
        border-bottom-color: {pal['tab_active_bg']};
        font-weight: 600;
    }}

    /* ---- buttons ------------------------------------------------------- */
    QPushButton {{
        background: {pal['surface_container']};
        border: 1px solid {pal['outline_variant']};
        border-radius: 7px;
        padding: 6px 14px;
        min-height: 18px;
    }}
    QPushButton:hover  {{ background: {pal['surface_container_high']}; }}
    QPushButton:pressed {{ background: {pal['surface_container_highest']}; }}
    QPushButton:disabled {{
        color: {pal['text_faint']};
        border-color: {pal['outline_variant']};
        background: {pal['surface_container_low']};
    }}
    QPushButton[accent="true"] {{
        background: {pal['primary']};
        border-color: {pal['primary_border']};
        color: {pal['on_primary']};
        font-weight: 600;
    }}
    QPushButton[accent="true"]:hover   {{ background: {pal['primary_hover']}; }}
    QPushButton[accent="true"]:disabled {{
        background: {pal['surface_container']};
        border-color: {pal['outline_variant']};
        color: {pal['text_faint']};
    }}
    QPushButton[toggle="true"] {{
        border-radius: 6px;
        padding: 4px 14px;
    }}
    QPushButton[toggle="true"]:checked {{
        background: {pal['primary']};
        border-color: {pal['primary_border']};
        color: {pal['on_primary']};
        font-weight: 600;
    }}

    /* ---- inputs -------------------------------------------------------- */
    QLineEdit, QComboBox {{
        background: {pal['surface_container_low']};
        border: 1px solid {pal['outline_variant']};
        border-radius: 7px;
        padding: 5px 9px;
        selection-background-color: {pal['primary']};
        selection-color: {pal['on_primary']};
    }}
    QLineEdit:focus, QComboBox:focus {{ border-color: {pal['primary']}; }}
    QLineEdit:disabled {{
        background: {pal['surface_container']};
        color: {pal['text_faint']};
    }}
    QComboBox QAbstractItemView {{
        background: {pal['surface_container_low']};
        border: 1px solid {pal['outline_variant']};
        selection-background-color: {pal['primary']};
        selection-color: {pal['on_primary']};
        outline: none;
    }}
    QCheckBox, QRadioButton {{ spacing: 7px; padding: 2px; }}
    QCheckBox::indicator, QRadioButton::indicator {{ width: 15px; height: 15px; }}
    QCheckBox::indicator {{
        border: 1px solid {pal['outline']};
        border-radius: 4px;
        background: {pal['surface_container_low']};
    }}
    QRadioButton::indicator {{
        border: 1px solid {pal['outline']};
        border-radius: 8px;
        background: {pal['surface_container_low']};
    }}
    QCheckBox::indicator:checked, QRadioButton::indicator:checked {{
        background: {pal['primary']};
        border-color: {pal['primary_border']};
    }}

    /* ---- group boxes --------------------------------------------------- */
    QGroupBox {{
        border: 1px solid {pal['outline_variant']};
        border-radius: 8px;
        margin-top: 14px;
        padding: 12px 10px 10px 10px;
        background: {pal['surface_container_low']};
    }}
    QGroupBox::title {{
        subcontrol-origin: margin;
        subcontrol-position: top left;
        left: 10px;
        padding: 0 6px;
        color: {pal['text_muted']};
        font-weight: 600;
    }}

    /* ---- tables -------------------------------------------------------- */
    QTableView {{
        background: {pal['surface_container_low']};
        alternate-background-color: {pal['surface_container']};
        border: 1px solid {pal['outline_variant']};
        border-radius: 8px;
        gridline-color: {pal['grid']};
        selection-background-color: {pal['selection']};
        selection-color: {pal['text']};
        outline: none;
    }}
    QTableView::item {{ padding: 3px 6px; border: none; }}
    QHeaderView::section {{
        background: {pal['surface_container_high']};
        color: {pal['text_muted']};
        border: none;
        border-right: 1px solid {pal['outline_variant']};
        border-bottom: 1px solid {pal['outline_variant']};
        padding: 6px 8px;
        font-weight: 600;
    }}
    QTableCornerButton::section {{
        background: {pal['surface_container_high']};
        border: none;
    }}

    /* ---- log ----------------------------------------------------------- */
    QPlainTextEdit {{
        background: {pal['surface_container_low']};
        border: 1px solid {pal['outline_variant']};
        border-radius: 8px;
        font-family: "{mono}";
        font-size: 9pt;
        selection-background-color: {pal['primary']};
        selection-color: {pal['on_primary']};
    }}

    /* ---- misc ---------------------------------------------------------- */
    QProgressBar {{
        border: 1px solid {pal['outline_variant']};
        border-radius: 7px;
        background: {pal['surface_container_low']};
        text-align: center;
        height: 18px;
    }}
    QProgressBar::chunk {{ background: {pal['primary']}; border-radius: 6px; }}
    QSplitter::handle {{ background: transparent; width: 6px; }}
    QScrollBar:vertical {{
        background: transparent; width: 11px; margin: 0;
    }}
    QScrollBar::handle:vertical {{
        background: {pal['outline_variant']};
        border-radius: 5px; min-height: 28px;
    }}
    QScrollBar::handle:vertical:hover {{ background: {pal['outline']}; }}
    QScrollBar:horizontal {{
        background: transparent; height: 11px; margin: 0;
    }}
    QScrollBar::handle:horizontal {{
        background: {pal['outline_variant']};
        border-radius: 5px; min-width: 28px;
    }}
    QScrollBar::handle:horizontal:hover {{ background: {pal['outline']}; }}
    QScrollBar::add-line, QScrollBar::sub-line {{ height: 0; width: 0; }}
    QScrollBar::add-page, QScrollBar::sub-page {{ background: transparent; }}
    QFrame[hline="true"] {{
        border: none;
        border-top: 1px solid {pal['outline_variant']};
        max-height: 1px;
    }}
    /* A 1px-wide frame has no room to paint a border, so fill it instead. */
    QFrame[vline="true"] {{
        border: none;
        background: {pal['outline_variant']};
        margin: 5px 0;
    }}
    QPushButton[danger="true"]:hover {{
        background: {pal['surface_container_high']};
        border-color: {pal['error']};
        color: {pal['error']};
    }}
    QListWidget {{
        background: {pal['surface_container_low']};
        border: 1px solid {pal['outline_variant']};
        border-radius: 8px;
        font-family: "{mono}";
        font-size: 9pt;
        outline: none;
    }}
    QListWidget::item:selected {{
        background: {pal['selection']};
        color: {pal['text']};
    }}
    QToolTip {{
        background: {pal['surface_container_highest']};
        color: {pal['text']};
        border: 1px solid {pal['outline_variant']};
        padding: 4px 7px;
    }}
    """
