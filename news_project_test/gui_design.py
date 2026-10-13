"""모든 GUI의 공통 디자인 관리.

색상·테두리·버튼 모양: STYLE
글꼴: FONT_FAMILY, FONT_POINT_SIZE
창 크기: WINDOW_SIZES, WINDOW_MINIMUM_SIZES
여백·간격·언론사 열 수: 아래 상수

각 *_gui.py는 화면 구성과 이벤트를 담당하고 이 모듈에서 디자인을 가져온다.
"""
from PySide6.QtGui import QFont
from PySide6.QtWidgets import QLabel, QPushButton, QVBoxLayout

FONT_FAMILY = "맑은 고딕"
FONT_POINT_SIZE = 10
QT_STYLE = "Fusion"

WINDOW_SIZES = {
    "main": (820, 580),
    "collection_menu": (570, 370),
    "settings": (680, 620),
    "media_selection": (760, 540),
    "collection_progress": (720, 510),
    "initialization": (660, 390),
}
WINDOW_MINIMUM_SIZES = {"main": (660, 480)}
PAGE_MARGINS = (28, 24, 28, 24)
PAGE_SPACING = 16
CARD_MARGINS = (24, 24, 24, 24)
CARD_SPACING = 15
FORM_SPACING = 13
MEDIA_COLUMNS = 3

STYLE = """
QWidget { background: #f3f6fb; color: #17243b; font-size: 14px; }
QDialog, QMainWindow { background: #f3f6fb; }
QFrame#card { background: white; border: 1px solid #dfe6f0; border-radius: 14px; }
QLabel { background: transparent; }
QLabel#title { font-size: 25px; font-weight: 700; }
QLabel#subtitle { color: #63718a; }
QPushButton { background: white; border: 1px solid #d4deed; border-radius: 8px;
              padding: 10px 18px; min-height: 20px; }
QPushButton:hover { background: #eaf1fc; border-color: #819ecd; }
QPushButton#primary { background: #2864df; color: white; border: none; }
QPushButton#primary:hover { background: #1e50bd; }
QPushButton#danger { color: #b52a3d; border-color: #e6b9c1; }
QPushButton:disabled { background: #e8edf4; color: #96a0b0; }
QLineEdit, QSpinBox, QPlainTextEdit { background: white; border: 1px solid #d4deed;
                                  border-radius: 7px; padding: 8px; }
QLineEdit:focus, QSpinBox:focus { border: 1px solid #2864df; }
QTabWidget::pane { border: 1px solid #dfe6f0; background: white; border-radius: 8px; }
QTabBar::tab { padding: 10px 16px; background: #e9eef6; }
QTabBar::tab:selected { background: white; color: #2864df; }
QCheckBox { padding: 9px; background: transparent; }
QProgressBar { border: 1px solid #d4deed; border-radius: 6px; text-align: center; min-height: 16px; }
QProgressBar::chunk { background: #2864df; border-radius: 5px; }
QScrollArea { border: none; }
"""

def apply_theme(app):
    app.setStyle(QT_STYLE)
    app.setFont(QFont(FONT_FAMILY, FONT_POINT_SIZE))
    app.setStyleSheet(STYLE)

def page_layout(widget, title, subtitle=""):
    layout = QVBoxLayout(widget)
    layout.setContentsMargins(*PAGE_MARGINS)
    layout.setSpacing(PAGE_SPACING)
    heading = QLabel(title)
    heading.setObjectName("title")
    layout.addWidget(heading)
    if subtitle:
        label = QLabel(subtitle)
        label.setWordWrap(True)
        label.setObjectName("subtitle")
        layout.addWidget(label)
    return layout

def button(text, callback=None, kind=""):
    item = QPushButton(text)
    item.setObjectName(kind)
    if callback:
        item.clicked.connect(callback)
    return item


def configure_window(window, name):
    """이름에 대응하는 초기 창 크기와 최소 크기를 적용한다."""
    window.resize(*WINDOW_SIZES[name])
    minimum = WINDOW_MINIMUM_SIZES.get(name)
    if minimum:
        window.setMinimumSize(*minimum)


def card_layout(card):
    """메인 화면 카드의 공통 디자인을 적용한다."""
    card.setObjectName("card")
    layout = QVBoxLayout(card)
    layout.setContentsMargins(*CARD_MARGINS)
    layout.setSpacing(CARD_SPACING)
    return layout