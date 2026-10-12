import tkinter as tk

import config

from collection.media_select.media_select_gui import MediaSelectionWindow
from setting.setting_gui import DatabaseSettingWindow
from collection import collection_gui as crawler_gui

APP_TITLE = "뉴스기사 수집 및 분석"
WINDOW_SIZE = "550x450"
SUB_WINDOW_SIZE = "500x200"
FONT_TITLE = ("Helvetica", 11, "bold")
FONT_NORMAL = ("Helvetica", 10)
FONT_BUTTON = ("Helvetica", 10, "bold")


def create_button(parent, text, command):
    return tk.Button(
        parent, text=text, width=35, height=2, font=FONT_BUTTON, command=command
    )


class NewsApp:
    """메인 화면과 각 기능 화면을 연결합니다."""

    def __init__(self, root):
        self.root = root
        self.root.title(APP_TITLE)
        self.root.geometry(WINDOW_SIZE)
        self.root.eval("tk::PlaceWindow . center")

        saved_selection = getattr(config, "SELECTED_RSS", [])
        self.check_vars = {
            category: {
                media: tk.BooleanVar(value=(media in saved_selection))
                for media in media_list
            }
            for category, media_list in config.MEDIA_RSS.items()
        }
        self.toggle_states = {category: False for category in config.MEDIA_RSS}

        self.setup_main_ui()

    def setup_main_ui(self):
        frame = tk.Frame(self.root, padx=30, pady=28)
        frame.pack(fill="both", expand=True)

        tk.Label(frame, text=APP_TITLE, font=FONT_TITLE).pack(pady=(8, 22))

        create_button(
            frame,
            "환경 설정",
            command=lambda: DatabaseSettingWindow(self.root),
        ).pack(pady=8)

        create_button(
            frame,
            "뉴스 수집하러가기",
            command=self.open_collection_menu,
        ).pack(pady=8)

        create_button(
            frame,
            "뉴스 분석하러가기",
            command=self.open_analysis_window,
        ).pack(pady=8)

    def open_collection_menu(self):
        """언론사 선택과 수집 시작 버튼이 있는 화면을 엽니다."""
        window = tk.Toplevel(self.root)
        window.title("뉴스 수집")
        window.geometry(SUB_WINDOW_SIZE)
        self.root.eval(f"tk::PlaceWindow {str(window)} center")

        frame = tk.Frame(window, padx=25, pady=25)
        frame.pack(fill="both", expand=True)
        tk.Label(frame, text="뉴스 수집", font=FONT_TITLE).pack(pady=(5, 20))

        create_button(
            frame,
            "언론사 선택",
            command=lambda: MediaSelectionWindow(
                window, self.check_vars, self.toggle_states
            ),
        ).pack(pady=8)

        create_button(
            frame,
            "뉴스 수집 시작",
            command=lambda: crawler_gui.CrawlerProgressWindow(
                window, self.check_vars
            ),
        ).pack(pady=8)

    def open_analysis_window(self):
        """분석 화면 진입점을 제공합니다."""
        window = tk.Toplevel(self.root)
        window.title("뉴스 분석")
        window.geometry(SUB_WINDOW_SIZE)
        self.root.eval(f"tk::PlaceWindow {str(window)} center")

        tk.Label(
            window,
            text="뉴스 분석 화면은 아직 준비 중입니다.",
            font=FONT_NORMAL,
            wraplength=420,
            justify="center",
        ).pack(expand=True, padx=25, pady=25)
