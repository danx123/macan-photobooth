"""
macan_pb_style.py
Charcoal enterprise theme for Macan PhotoBooth.
Labels are transparent by design so panel backgrounds show through cleanly.
"""

ACCENT = "#e0a030"          # macan amber accent
ACCENT_DIM = "#8a6423"
BG_APP = "#232323"
BG_PANEL = "#2b2b2b"
BG_PANEL_ALT = "#262626"
BG_INPUT = "#3a3a3a"
BORDER = "#454545"
BORDER_LIGHT = "#5a5a5a"
TEXT = "#e6e6e6"
TEXT_DIM = "#9a9a9a"
DANGER = "#c0453b"
SUCCESS = "#4caf6a"

CHARCOAL_QSS = f"""
QWidget {{
    background-color: {BG_APP};
    color: {TEXT};
    font-family: "Segoe UI", "Inter", "Ubuntu", sans-serif;
    font-size: 13px;
}}

QMainWindow {{
    background-color: {BG_APP};
}}

QMenuBar {{
    background-color: {BG_APP};
    color: {TEXT};
    border-bottom: 1px solid {BORDER};
    padding: 2px 4px;
}}
QMenuBar::item {{
    background: transparent;
    padding: 6px 12px;
    border-radius: 4px;
}}
QMenuBar::item:selected {{
    background-color: {BG_INPUT};
    color: {ACCENT};
}}
QMenuBar::item:pressed {{
    background-color: {ACCENT_DIM};
    color: #ffffff;
}}

QMenu {{
    background-color: {BG_PANEL};
    border: 1px solid {BORDER_LIGHT};
    padding: 4px;
}}
QMenu::item {{
    background: transparent;
    color: {TEXT};
    padding: 6px 28px 6px 14px;
    border-radius: 4px;
}}
QMenu::item:selected {{
    background-color: {ACCENT_DIM};
    color: #ffffff;
}}
QMenu::item:disabled {{
    color: #6b6b6b;
}}
QMenu::separator {{
    height: 1px;
    background: {BORDER};
    margin: 4px 6px;
}}

QToolBar {{
    background-color: {BG_APP};
    border-bottom: 1px solid {BORDER};
    spacing: 4px;
    padding: 4px 6px;
}}
QToolBar::separator {{
    background: {BORDER};
    width: 1px;
    margin: 4px 6px;
}}
QToolButton {{
    background: transparent;
    border: 1px solid transparent;
    border-radius: 4px;
    padding: 6px 12px;
    color: {TEXT};
}}
QToolButton:hover {{
    background-color: {BG_INPUT};
    border-color: {ACCENT_DIM};
    color: {ACCENT};
}}
QToolButton:pressed {{
    background-color: {ACCENT_DIM};
    color: #ffffff;
}}
QToolButton:disabled {{
    color: #6b6b6b;
}}

QTabBar::tab {{
    background-color: {BG_PANEL_ALT};
    color: {TEXT_DIM};
    border: 1px solid {BORDER};
    border-bottom: none;
    padding: 6px 12px;
}}
QTabBar::tab:selected {{
    background-color: {BG_PANEL};
    color: {ACCENT};
}}
QTabBar::tab:hover {{
    background-color: #383838;
    color: {TEXT};
}}

/* Panels are frames with a subtle border, labels inside them stay transparent */
QFrame#panel {{
    background-color: {BG_PANEL};
    border: 1px solid {BORDER};
    border-radius: 6px;
}}

QFrame#liveViewFrame {{
    background-color: #101010;
    border: 1px solid {BORDER};
    border-radius: 6px;
}}

QLabel {{
    background: transparent;
}}

QLabel#panelTitle {{
    background: transparent;
    color: {TEXT_DIM};
    font-weight: 600;
    font-size: 11px;
    letter-spacing: 1px;
    padding: 6px 8px 2px 8px;
}}

QLabel#countdownLabel {{
    background: transparent;
    color: {ACCENT};
    font-size: 220px;
    font-weight: 800;
}}

QLabel#readyLabel {{
    background: transparent;
    color: {ACCENT};
    font-size: 54px;
    font-weight: 700;
    letter-spacing: 6px;
}}

QLabel#framePreviewCaption {{
    background: transparent;
    color: {TEXT_DIM};
    font-size: 11px;
    padding: 4px;
}}

QLabel#sessionHint {{
    background: transparent;
    color: {TEXT_DIM};
    font-size: 13px;
}}

QPushButton {{
    background-color: {BG_INPUT};
    border: 1px solid {BORDER_LIGHT};
    border-radius: 6px;
    padding: 8px 16px;
    color: {TEXT};
}}
QPushButton:hover {{
    background-color: #474747;
    border-color: {ACCENT_DIM};
}}
QPushButton:pressed {{
    background-color: #303030;
}}
QPushButton:disabled {{
    color: #6b6b6b;
    background-color: #313131;
    border-color: #3a3a3a;
}}

QPushButton#primaryButton {{
    background-color: {ACCENT};
    border: 1px solid {ACCENT};
    color: #1c1c1c;
    font-weight: 700;
}}
QPushButton#primaryButton:hover {{
    background-color: #ecb254;
}}
QPushButton#primaryButton:disabled {{
    background-color: #5b4a2c;
    color: #8a8a8a;
    border-color: #5b4a2c;
}}

QPushButton#dangerButton {{
    background-color: transparent;
    border: 1px solid {DANGER};
    color: {DANGER};
}}
QPushButton#dangerButton:hover {{
    background-color: {DANGER};
    color: #ffffff;
}}

QPushButton#templateButton {{
    background-color: {BG_PANEL_ALT};
    border: 1px solid {BORDER};
    border-radius: 8px;
    padding: 6px;
}}
QPushButton#templateButton:checked {{
    border: 2px solid {ACCENT};
    background-color: #383021;
}}

QComboBox, QSpinBox {{
    background-color: {BG_INPUT};
    border: 1px solid {BORDER_LIGHT};
    border-radius: 4px;
    padding: 5px 8px;
    color: {TEXT};
}}
QComboBox::drop-down {{
    border: none;
    width: 20px;
}}
QComboBox QAbstractItemView {{
    background-color: {BG_INPUT};
    selection-background-color: {ACCENT_DIM};
    color: {TEXT};
    outline: none;
}}

QTreeView, QListWidget, QListView {{
    background-color: {BG_PANEL_ALT};
    border: 1px solid {BORDER};
    border-radius: 4px;
    color: {TEXT};
    outline: none;
}}
QTreeView::item, QListWidget::item {{
    padding: 3px;
}}
QTreeView::item:selected, QListWidget::item:selected {{
    background-color: {ACCENT_DIM};
    color: #ffffff;
}}
QHeaderView::section {{
    background-color: {BG_PANEL};
    color: {TEXT_DIM};
    border: none;
    padding: 4px;
}}

QScrollBar:vertical {{
    background: {BG_PANEL_ALT};
    width: 10px;
    margin: 0;
}}
QScrollBar::handle:vertical {{
    background: {BORDER_LIGHT};
    border-radius: 5px;
    min-height: 24px;
}}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
    height: 0;
}}
QScrollBar:horizontal {{
    background: {BG_PANEL_ALT};
    height: 10px;
}}
QScrollBar::handle:horizontal {{
    background: {BORDER_LIGHT};
    border-radius: 5px;
    min-width: 24px;
}}

QStatusBar {{
    background-color: {BG_PANEL};
    color: {TEXT_DIM};
    border-top: 1px solid {BORDER};
}}

QToolTip {{
    background-color: {BG_INPUT};
    color: {TEXT};
    border: 1px solid {BORDER_LIGHT};
    padding: 4px;
}}

QDialog {{
    background-color: {BG_APP};
}}

QGroupBox {{
    border: 1px solid {BORDER};
    border-radius: 6px;
    margin-top: 10px;
    padding-top: 12px;
    color: {TEXT_DIM};
    font-weight: 600;
}}
QGroupBox::title {{
    subcontrol-origin: margin;
    left: 10px;
    padding: 0 4px;
}}

QProgressBar {{
    background-color: {BG_INPUT};
    border: 1px solid {BORDER};
    border-radius: 4px;
    text-align: center;
    color: {TEXT};
}}
QProgressBar::chunk {{
    background-color: {ACCENT};
    border-radius: 3px;
}}
"""
