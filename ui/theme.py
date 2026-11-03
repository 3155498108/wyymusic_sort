"""网易云风格主题（深色 + 红色主色）

集中管理配色与全局 QSS，所有窗口共用：
    from ui.theme import apply_theme
    apply_theme(app)      # QApplication 创建后调用一次
"""
import os
import sys
import tempfile

from PyQt6.QtGui import QColor, QFont, QIcon, QPainter, QPen, QPixmap
from PyQt6.QtCore import Qt, QPointF

# ---------------- 配色 ----------------
RED = "#EC4141"
RED_HOVER = "#F25555"
RED_PRESSED = "#D83838"

BG = "#1E1E1E"          # 主内容区
BG_SIDEBAR = "#191919"  # 左侧栏
BG_CARD = "#252525"     # 卡片
BG_INPUT = "#2A2A2A"
BG_HOVER = "#2A2A2A"
BG_ACTIVE = "#333333"
LINE = "#2B2B2B"

TEXT = "#E9E9E9"
TEXT_SUB = "#A8A8A8"
TEXT_WEAK = "#757575"
TEXT_DIM = "#5F5F5F"

_ASSET_DIR = os.path.join(tempfile.gettempdir(), "ncm_sort_theme")


def _asset_path(name: str) -> str:
    return os.path.join(_ASSET_DIR, name).replace("\\", "/")


def _ensure_assets() -> None:
    """生成 QSS 需要的小图标（对勾 / 下拉箭头），避免依赖外部图片资源"""
    os.makedirs(_ASSET_DIR, exist_ok=True)

    check = _asset_path("check.png")
    if not os.path.exists(check):
        pm = QPixmap(24, 24)
        pm.fill(Qt.GlobalColor.transparent)
        p = QPainter(pm)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        pen = QPen(QColor("#FFFFFF"))
        pen.setWidth(3)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        p.setPen(pen)
        p.drawPolyline(QPointF(6, 12.5), QPointF(10.5, 17), QPointF(18, 7.5))
        p.end()
        pm.save(check, "PNG")

    arrow = _asset_path("arrow.png")
    if not os.path.exists(arrow):
        pm = QPixmap(20, 20)
        pm.fill(Qt.GlobalColor.transparent)
        p = QPainter(pm)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        pen = QPen(QColor("#9A9A9A"))
        pen.setWidth(2)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        p.setPen(pen)
        p.drawPolyline(QPointF(6, 8), QPointF(10, 12.5), QPointF(14, 8))
        p.end()
        pm.save(arrow, "PNG")


def stylesheet() -> str:
    _ensure_assets()
    return f"""
/* ---------------- 基础 ---------------- */
QWidget {{
    background: transparent;
    color: {TEXT};
    font-family: "Microsoft YaHei UI", "Microsoft YaHei", "PingFang SC", sans-serif;
    font-size: 13px;
}}
QWidget#central, QWidget#content {{ background: {BG}; }}
QWidget#sidebar {{
    background: {BG_SIDEBAR};
    border-right: 1px solid #232323;
}}
QWidget#card {{
    background: {BG_CARD};
    border-radius: 10px;
}}
QWidget#bottombar {{
    background: #232323;
    border-top: 1px solid #2A2A2A;
}}
QDialog {{ background: #1F1F1F; }}

/* ---------------- 文本 ---------------- */
QLabel {{ color: #D2D2D2; }}
QLabel[variant="h1"] {{ color: #F2F2F2; font-size: 20px; font-weight: 600; }}
QLabel[variant="section"] {{ color: {TEXT_WEAK}; font-size: 12px; }}
QLabel[variant="sub"] {{ color: #8C8C8C; font-size: 12px; }}
QLabel[variant="weak"] {{ color: {TEXT_WEAK}; font-size: 12px; }}
QLabel[variant="brand"] {{ color: #F4F4F4; font-size: 14px; font-weight: 600; }}
QLabel#logo {{
    background: {RED};
    border-radius: 13px;
    color: #FFFFFF;
    font-size: 15px;
    font-weight: bold;
}}

/* ---------------- 按钮 ---------------- */
QPushButton {{
    background: #2B2B2B;
    color: #DEDEDE;
    border: 1px solid #343434;
    border-radius: 7px;
    padding: 6px 14px;
    font-size: 13px;
}}
QPushButton:hover {{ background: #353535; border-color: #3F3F3F; }}
QPushButton:pressed {{ background: #262626; }}
QPushButton:disabled {{ color: #5A5A5A; background: #232323; border-color: #2A2A2A; }}

QPushButton[variant="primary"] {{
    background: {RED};
    border: none;
    color: #FFFFFF;
    font-weight: 600;
}}
QPushButton[variant="primary"]:hover {{ background: {RED_HOVER}; }}
QPushButton[variant="primary"]:pressed {{ background: {RED_PRESSED}; }}
QPushButton[variant="primary"]:disabled {{ background: #4A2A2A; color: #A98484; }}

QPushButton[variant="ghost"] {{
    background: transparent;
    border: none;
    color: #B2B2B2;
    padding: 5px 8px;
}}
QPushButton[variant="ghost"]:hover {{ background: #2A2A2A; color: #FFFFFF; }}
QPushButton[variant="ghost"]:disabled {{ color: #565656; background: transparent; }}

QPushButton[variant="round"] {{
    background: {RED};
    border: none;
    border-radius: 18px;
    color: #FFFFFF;
    font-size: 14px;
    padding: 0;
}}
QPushButton[variant="round"]:hover {{ background: {RED_HOVER}; }}
QPushButton[variant="round"]:disabled {{ background: #4A2A2A; color: #A98484; }}

QPushButton[variant="search"] {{
    background: #262626;
    border: 1px solid #303030;
    border-radius: 16px;
    color: #8A8A8A;
    text-align: left;
    padding: 0 16px;
    font-size: 13px;
}}
QPushButton[variant="search"]:hover {{ background: #2D2D2D; color: #C6C6C6; border-color: #3A3A3A; }}

/* ---------------- 输入 ---------------- */
QLineEdit, QTextEdit, QPlainTextEdit {{
    background: {BG_INPUT};
    border: 1px solid #343434;
    border-radius: 7px;
    color: #E8E8E8;
    padding: 7px 10px;
    selection-background-color: {RED};
    selection-color: #FFFFFF;
}}
QLineEdit:focus, QTextEdit:focus, QPlainTextEdit:focus {{ border-color: {RED}; }}
QLineEdit:read-only {{ color: #A0A0A0; }}

/* ---------------- 下拉 ---------------- */
QComboBox {{
    background: {BG_INPUT};
    border: 1px solid #343434;
    border-radius: 7px;
    color: #DCDCDC;
    padding: 5px 10px;
    min-height: 20px;
}}
QComboBox:hover {{ border-color: #454545; }}
QComboBox::drop-down {{ border: none; width: 20px; }}
QComboBox::down-arrow {{ image: url({_asset_path('arrow.png')}); width: 10px; height: 10px; }}
QComboBox QAbstractItemView {{
    background: #262626;
    border: 1px solid #363636;
    border-radius: 6px;
    color: #DCDCDC;
    selection-background-color: {RED};
    selection-color: #FFFFFF;
    outline: none;
    padding: 4px;
}}

/* ---------------- 列表 ---------------- */
QListWidget {{ background: transparent; border: none; outline: none; }}
QListWidget::item {{
    color: #B9B9B9;
    padding: 0 10px;
    border-radius: 6px;
    min-height: 32px;
}}
QListWidget::item:hover {{ background: #232323; color: #EDEDED; }}
QListWidget::item:selected {{
    background: #303030;
    color: #FFFFFF;
    border-left: 3px solid {RED};
}}

/* ---------------- 表格 ---------------- */
QTableWidget {{
    background: transparent;
    border: none;
    gridline-color: transparent;
    outline: none;
}}
QTableWidget::item {{
    color: #C4C4C4;
    border: none;
    padding-left: 8px;
}}
QTableWidget::item:hover {{ background: {BG_HOVER}; }}
QTableWidget::item:selected {{ background: {BG_ACTIVE}; color: #FFFFFF; }}
QHeaderView {{ background: transparent; }}
QHeaderView::section {{
    background: transparent;
    color: #8A8A8A;
    border: none;
    padding: 8px 6px;
    font-size: 12px;
}}
QTableCornerButton::section {{ background: transparent; border: none; }}
QTableWidget::indicator {{
    width: 15px;
    height: 15px;
    border-radius: 4px;
    border: 1px solid #4A4A4A;
    background: #242424;
}}
QTableWidget::indicator:hover {{ border-color: #6A6A6A; }}
QTableWidget::indicator:checked {{
    background: {RED};
    border-color: {RED};
    image: url({_asset_path('check.png')});
}}

/* ---------------- 滚动条 ---------------- */
QScrollBar:vertical {{ background: transparent; width: 9px; margin: 2px 2px 2px 0; }}
QScrollBar::handle:vertical {{ background: #3A3A3A; border-radius: 4px; min-height: 32px; }}
QScrollBar::handle:vertical:hover {{ background: #4C4C4C; }}
QScrollBar:horizontal {{ background: transparent; height: 9px; margin: 0 2px 2px 2px; }}
QScrollBar::handle:horizontal {{ background: #3A3A3A; border-radius: 4px; min-width: 32px; }}
QScrollBar::handle:horizontal:hover {{ background: #4C4C4C; }}
QScrollBar::add-line, QScrollBar::sub-line {{ width: 0; height: 0; }}
QScrollBar::add-page, QScrollBar::sub-page {{ background: transparent; }}

/* ---------------- 勾选 ---------------- */
QCheckBox {{ color: #B5B5B5; spacing: 8px; font-size: 12px; }}
QCheckBox::indicator {{
    width: 15px;
    height: 15px;
    border-radius: 4px;
    border: 1px solid #4A4A4A;
    background: #242424;
}}
QCheckBox::indicator:hover {{ border-color: #6A6A6A; }}
QCheckBox::indicator:checked {{
    background: {RED};
    border-color: {RED};
    image: url({_asset_path('check.png')});
}}

/* ---------------- 其他 ---------------- */
QGroupBox {{
    border: 1px solid #2C2C2C;
    border-radius: 9px;
    margin-top: 12px;
    padding-top: 6px;
    color: #8A8A8A;
    font-size: 12px;
}}
QGroupBox::title {{
    subcontrol-origin: margin;
    left: 12px;
    padding: 0 6px;
    color: #8A8A8A;
}}
QProgressBar {{ background: #2A2A2A; border: none; border-radius: 3px; }}
QProgressBar::chunk {{ background: {RED}; border-radius: 3px; }}
QScrollArea {{ border: none; background: transparent; }}
QToolTip {{
    background: #2A2A2A;
    color: #DDDDDD;
    border: 1px solid #3A3A3A;
    padding: 6px 8px;
}}
QMenu {{ background: #262626; border: 1px solid #363636; padding: 4px; }}
QMenu::item {{ padding: 6px 22px; border-radius: 5px; color: #D8D8D8; }}
QMenu::item:selected {{ background: {RED}; color: #FFFFFF; }}
QMessageBox {{ background: #232323; }}
QMessageBox QLabel {{ color: #D8D8D8; }}
"""


def app_icon() -> QIcon:
    """红色圆形 + 音符图标，作为窗口/任务栏图标"""
    pm = QPixmap(64, 64)
    pm.fill(Qt.GlobalColor.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setBrush(QColor(RED))
    p.setPen(Qt.PenStyle.NoPen)
    p.drawEllipse(2, 2, 60, 60)
    p.setPen(QColor("#FFFFFF"))
    f = QFont("Microsoft YaHei UI", 30)
    f.setBold(True)
    p.setFont(f)
    p.drawText(pm.rect(), Qt.AlignmentFlag.AlignCenter, "♪")
    p.end()
    return QIcon(pm)


def apply_theme(app) -> None:
    """给整个应用套用网易云风格主题"""
    _ensure_assets()
    font = QFont("Microsoft YaHei UI", 9)
    font.setStyleHint(QFont.StyleHint.SansSerif)
    app.setFont(font)
    app.setStyleSheet(stylesheet())
    app.setWindowIcon(app_icon())


def apply_dark_title_bar(widget) -> None:
    """让 Windows 原生标题栏也变成深色（Win10 1809+ 支持），避免黑白割裂"""
    if sys.platform != "win32":
        return
    try:
        import ctypes

        hwnd = int(widget.winId())
        value = ctypes.c_int(1)
        for attr in (20, 19):  # DWMWA_USE_IMMERSIVE_DARK_MODE（旧版本是 19）
            if ctypes.windll.dwmapi.DwmSetWindowAttribute(
                hwnd, attr, ctypes.byref(value), ctypes.sizeof(value)
            ) == 0:
                break
    except Exception:
        pass
