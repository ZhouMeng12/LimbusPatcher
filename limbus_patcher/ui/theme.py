"""低饱和暗色主题：深灰黑底 / 炭灰面板 / 暗金强调。"""
from __future__ import annotations

from PySide6.QtGui import QColor, QPalette
from PySide6.QtWidgets import QApplication

BG = "#121417"
PANEL = "#1b1f24"
PANEL_LIGHT = "#22272e"
ACCENT = "#c8a24a"
ACCENT_DARK = "#8f7434"
SUCCESS = "#5fa08a"
WARNING = "#d9a441"
ERROR = "#b45f4d"
TEXT = "#d8d4c8"
TEXT_DIM = "#8b867a"
BORDER = "#2c323a"
HOVER = "#262c34"
SELECTION = "#2a2f26"

CHIP_QSS = (
    "QLabel#chip {{ background: #23282f; border: 1px solid {color}; color: {color};"
    " padding: 2px 10px; border-radius: 10px; font-size: 12px; }}"
)

QSS = f"""
* {{
    font-family: "Microsoft YaHei UI", "Microsoft YaHei", "Segoe UI", sans-serif;
    font-size: 13px;
    color: {TEXT};
}}
QMainWindow, QDialog {{ background: {BG}; }}
QWidget {{ background: transparent; }}
QFrame#panel {{ background: {PANEL}; border: 1px solid {BORDER}; border-radius: 6px; }}
QFrame#topbar {{ background: {PANEL}; border-bottom: 1px solid {BORDER}; }}
QLabel {{ background: transparent; }}
QLabel#title {{ font-size: 15px; font-weight: 600; color: {TEXT}; }}
QLabel#dim {{ color: {TEXT_DIM}; }}
QLabel#h1 {{ font-size: 20px; font-weight: 700; color: {TEXT}; }}
QLabel#chip {{ padding: 2px 8px; border-radius: 9px; font-size: 12px; }}
QPushButton {{
    background: {PANEL_LIGHT};
    border: 1px solid {BORDER};
    border-radius: 4px;
    padding: 5px 14px;
}}
QPushButton:hover {{ background: {HOVER}; border-color: {ACCENT_DARK}; }}
QPushButton:pressed {{ background: {SELECTION}; }}
QPushButton:disabled {{ color: {TEXT_DIM}; background: {PANEL}; }}
QPushButton#primary {{
    background: {ACCENT_DARK};
    border-color: {ACCENT};
    color: #141210;
    font-weight: 600;
}}
QPushButton#primary:hover {{ background: {ACCENT}; }}
QPushButton#danger {{ border-color: {ERROR}; color: {ERROR}; }}
QPushButton#danger:hover {{ background: {ERROR}; color: #141210; }}
QLineEdit, QComboBox, QPlainTextEdit, QTextEdit, QListView, QListWidget {{
    background: {BG};
    border: 1px solid {BORDER};
    border-radius: 4px;
    padding: 4px 6px;
    selection-background-color: {ACCENT_DARK};
    selection-color: #141210;
}}
QLineEdit:focus, QPlainTextEdit:focus, QTextEdit:focus, QComboBox:focus {{
    border-color: {ACCENT_DARK};
}}
QPlainTextEdit#original {{
    background: {PANEL};
    color: {TEXT_DIM};
    border: 1px dashed {BORDER};
}}
QListView::item {{ padding: 4px; border-radius: 4px; }}
QListView::item:hover {{ background: {HOVER}; }}
QListView::item:selected {{ background: {SELECTION}; border-left: 3px solid {ACCENT}; }}
QListWidget::item {{ padding: 6px; border-radius: 4px; }}
QListWidget::item:hover {{ background: {HOVER}; }}
QListWidget::item:selected {{ background: {SELECTION}; border-left: 3px solid {ACCENT}; }}
QComboBox::drop-down {{ border: none; width: 18px; }}
QComboBox QAbstractItemView {{ background: {PANEL}; border: 1px solid {BORDER}; selection-background-color: {ACCENT_DARK}; }}
QScrollBar:vertical {{ background: {BG}; width: 10px; margin: 0; }}
QScrollBar::handle:vertical {{ background: {BORDER}; border-radius: 5px; min-height: 24px; }}
QScrollBar::handle:vertical:hover {{ background: {ACCENT_DARK}; }}
QScrollBar::add-line, QScrollBar::sub-line {{ height: 0; width: 0; }}
QScrollBar:horizontal {{ background: {BG}; height: 10px; margin: 0; }}
QScrollBar::handle:horizontal {{ background: {BORDER}; border-radius: 5px; min-width: 24px; }}
QScrollBar::add-page, QScrollBar::sub-page {{ background: transparent; }}
QSplitter::handle {{ background: {BORDER}; }}
QSplitter::handle:horizontal {{ width: 1px; }}
QSplitter::handle:vertical {{ height: 1px; }}
QToolTip {{ background: {PANEL_LIGHT}; color: {TEXT}; border: 1px solid {BORDER}; padding: 4px; }}
QCheckBox::indicator {{ width: 14px; height: 14px; border: 1px solid {BORDER}; border-radius: 3px; background: {BG}; }}
QCheckBox::indicator:checked {{ background: {ACCENT_DARK}; border-color: {ACCENT}; }}
QProgressBar {{ background: {BG}; border: 1px solid {BORDER}; border-radius: 4px; text-align: center; }}
QProgressBar::chunk {{ background: {ACCENT_DARK}; border-radius: 3px; }}
QStatusBar {{ background: {PANEL}; color: {TEXT_DIM}; }}
QMessageBox, QInputDialog {{ background: {PANEL}; }}
QMenu {{ background: {PANEL_LIGHT}; border: 1px solid {BORDER}; }}
QMenu::item {{ padding: 5px 22px; }}
QMenu::item:selected {{ background: {ACCENT_DARK}; color: #141210; }}
"""


def apply_theme(app: QApplication) -> None:
    app.setStyleSheet(QSS)
    palette = QPalette()
    palette.setColor(QPalette.Window, QColor(BG))
    palette.setColor(QPalette.Base, QColor(BG))
    palette.setColor(QPalette.WindowText, QColor(TEXT))
    palette.setColor(QPalette.Text, QColor(TEXT))
    palette.setColor(QPalette.Button, QColor(PANEL_LIGHT))
    palette.setColor(QPalette.ButtonText, QColor(TEXT))
    palette.setColor(QPalette.Highlight, QColor(ACCENT_DARK))
    palette.setColor(QPalette.HighlightedText, QColor("#141210"))
    palette.setColor(QPalette.ToolTipBase, QColor(PANEL_LIGHT))
    palette.setColor(QPalette.ToolTipText, QColor(TEXT))
    app.setPalette(palette)
