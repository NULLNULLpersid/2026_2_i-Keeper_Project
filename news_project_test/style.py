"""
모든 GUI의 공통 디자인 관리.

색상·테두리·버튼 모양: STYLE
글꼴: FONT_FAMILY, FONT_POINT_SIZE
창 크기: WINDOW_SIZES, WINDOW_MINIMUM_SIZES
여백·간격·언론사 열 수: 아래 상수

각 *_gui.py는 화면 구성과 이벤트를 담당하고 이 모듈에서 디자인을 가져온다.
"""
from PySide6.QtGui import QFont, QColor, QPalette
from PySide6.QtWidgets import QLabel, QPushButton, QVBoxLayout

FONT_FAMILY = "맑은 고딕"
FONT_POINT_SIZE = 10
QT_STYLE = "Fusion"

WINDOW_SIZES = {
    "main": (460, 390),
    "collection_menu": (420, 370),
    "settings": (920, 550),
    "media_selection": (760, 540),
    "collection_progress": (720, 510),
    "initialization": (660, 390),
}
WINDOW_MINIMUM_SIZES = {"main": (420, 350), "collection_menu": (360, 320), "settings": (820, 500)}
PAGE_MARGINS = (28, 24, 28, 24)
PAGE_SPACING = 16
CARD_MARGINS = (24, 24, 24, 24)
CARD_SPACING = 15
FORM_SPACING = 13
MEDIA_COLUMNS = 3

THEMES = {
    "light": {
        "background": "#f3f6fb", "text": "#17243b", "surface": "#ffffff",
        "border": "#d4deed", "muted": "#63718a", "hover": "#eaf1fc",
        "disabled": "#e8edf4", "disabled_text": "#96a0b0", "tab": "#e9eef6",
    },
    "dark": {
        "background": "#171a21", "text": "#eef2f7", "surface": "#242a35",
        "border": "#465167", "muted": "#b1bdd1", "hover": "#343e50",
        "disabled": "#303641", "disabled_text": "#8290a4", "tab": "#303744",
    },
}

STYLE_TEMPLATE = """
QWidget { background: $background; color: $text; font-size: 14px; }
QFrame#card, QGroupBox { background: $surface; border: 1px solid $border; border-radius: 12px; }
QGroupBox { margin-top: 16px; padding: 18px 12px 12px; }
QGroupBox::title { subcontrol-origin: margin; left: 14px; padding: 0 5px; font-weight: 700; }
QLabel, QCheckBox, QRadioButton { background: transparent; }
QLabel#title { font-size: 25px; font-weight: 700; }
QLabel#subtitle { color: $muted; }
QPushButton { background: $surface; border: 1px solid $border; border-radius: 8px;
              padding: 10px 18px; min-height: 20px; }
QPushButton:hover { background: $hover; border-color: #819ecd; }
QPushButton#primary { background: #2864df; color: white; border: none; }
QPushButton#primary:hover { background: #1e50bd; }
QPushButton#danger { color: #e05a6d; border-color: #b94b60; }
QPushButton#success { background: #248445; color: white; border: none; }
QPushButton#success:hover { background: #196a35; }
QPushButton:disabled { background: $disabled; color: $disabled_text; }
QLineEdit, QPlainTextEdit { background: $surface; border: 1px solid $border;
                           border-radius: 7px; padding: 8px; }
QLineEdit:focus { border: 1px solid #2864df; }
QTabWidget::pane { border: 1px solid $border; background: $surface; border-radius: 8px; }
QTabBar::tab { padding: 10px 16px; background: $tab; }
QTabBar::tab:selected { background: $surface; color: #638ef3; }
QCheckBox, QRadioButton { padding: 6px; }
QProgressBar { border: 1px solid $border; border-radius: 6px; text-align: center; min-height: 16px; }
QProgressBar::chunk { background: #2864df; border-radius: 5px; }
QScrollArea { border: none; }
"""

def stylesheet(theme):
    colors = THEMES.get(theme, THEMES["light"])
    result = STYLE_TEMPLATE
    for name in sorted(colors, key=len, reverse=True):
        value = colors[name]
        result = result.replace("$" + name, value)
    return result

STYLE = stylesheet("light")

def apply_theme(app, theme=None):
    if theme is None:
        from init import config
        theme = getattr(config, "UI_THEME", "light")
    colors = THEMES.get(theme, THEMES["light"])
    if app.style().objectName().lower() != QT_STYLE.lower():
        app.setStyle(QT_STYLE)
    app.setFont(QFont(FONT_FAMILY, FONT_POINT_SIZE))
    palette = QPalette()
    for role, key in [
        (QPalette.ColorRole.Window, "background"),
        (QPalette.ColorRole.WindowText, "text"),
        (QPalette.ColorRole.Base, "surface"),
        (QPalette.ColorRole.AlternateBase, "background"),
        (QPalette.ColorRole.Text, "text"),
        (QPalette.ColorRole.Button, "surface"),
        (QPalette.ColorRole.ButtonText, "text"),
        (QPalette.ColorRole.ToolTipBase, "surface"),
        (QPalette.ColorRole.ToolTipText, "text"),
    ]:
        palette.setColor(role, QColor(colors[key]))
    palette.setColor(QPalette.ColorRole.Highlight, QColor("#2864df"))
    palette.setColor(QPalette.ColorRole.HighlightedText, QColor("#ffffff"))
    app.setPalette(palette)
    app.setStyleSheet(stylesheet(theme))

def set_button_kind(item, kind):
    item.setObjectName(kind)
    item.style().unpolish(item)
    item.style().polish(item)
    item.update()

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