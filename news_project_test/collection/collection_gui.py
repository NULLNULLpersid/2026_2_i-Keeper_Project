import logging
from queue import Queue, Empty
import os
import threading
import tkinter as tk
from tkinter import messagebox

import config
from collection import collection
from .media_select import media_select

WINDOW_SIZE = "500x200"
FONT_TITLE = ("Helvetica", 14, "bold")
FONT_SMALL = ("Helvetica", 8)
COLOR_STOP = "#c62828"
MSG_WARNING_TITLE = "경고"
MSG_ERROR_TITLE = "오류"
MSG_NO_PATH = "뉴스를 저장할 폴더 위치를 선택해주세요."
MSG_NO_PG_PATH = "PostgreSQL 경로가 비어있습니다. 경로를 설정해주세요."
MSG_INVALID_PG_PATH = (
    "PostgreSQL 경로가 유효하지 않습니다.\n"
    "설정된 경로가 실제 존재하는 'bin' 폴더인지 확인해주세요."
)
MSG_NO_MEDIA = "수집할 언론사가 하나도 선택되지 않았습니다. 언론사를 먼저 선택해주세요."

class CrawlerProgressWindow:
    """뉴스 수집을 시작하고 진행 상태와 종료 동작을 관리합니다."""

    def __init__(self, parent, check_vars):
        self.parent = parent
        self.check_vars = check_vars
        self.cancel_event = threading.Event()
        self.is_collecting = False
        self.logger = None
        self.save_path = ""
        self.selected_rss = media_select.build_selected_feeds(
            config.MEDIA_RSS, media_select.get_selected_media(self.check_vars)
        )

        if not self.selected_rss:
            messagebox.showwarning(
                MSG_WARNING_TITLE,
                MSG_NO_MEDIA,
                parent=self.window,
            )
            self._destroy_window()
            return

        self.save_path = save_path
        try:
            self.setup_file_logger()
        except OSError as exc:
            messagebox.showerror(
                MSG_ERROR_TITLE,
                f"로그 파일을 만들 수 없습니다. 저장 경로를 확인해주세요.\n{exc}",
                parent=self.window,
            )
            self._destroy_window()
            return

        self.is_collecting = True
        self.cancel_event.clear()
        self._append_log("수집을 시작했습니다.")
        self.logger.info("=== 뉴스 수집을 시작합니다. ===")
        self.thread = threading.Thread(target=self.run_task, daemon=True)
        self.thread.start()
        self.window.after(100, self._poll_messages)

    def setup_file_logger(self):
        os.makedirs(self.save_path, exist_ok=True)
        log_file = os.path.join(self.save_path, "crawler_error.log")
        self.logger = logging.getLogger(f"CrawlerLogger-{id(self)}")
        self.logger.setLevel(logging.DEBUG)
        self.logger.propagate = False

        handler = logging.FileHandler(log_file, encoding="utf-8")
        handler.setLevel(logging.DEBUG)
        handler.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(message)s"))
        self.logger.addHandler(handler)

    def update_ui_log(self, message):
        if not self._closed:
            self._messages.put(message)

    def _poll_messages(self):
        # Tk 메서드는 메인 스레드에서만 실행한다.
        if self._closed:
            return
        try:
            while True:
                self._append_log(self._messages.get_nowait())
        except Empty:
            pass
        if self._finished.is_set():
            if self._error:
                messagebox.showerror(MSG_ERROR_TITLE, self._error, parent=self.window)
            self.on_finish()
        else:
            self.window.after(100, self._poll_messages)

    def _on_destroy(self, event):
        if event.widget is self.window:
            self._closed = True
            self.cancel_event.set()

    def _append_log(self, message):
        if self._closed:
            return
        try:
            self.log_listbox.insert(tk.END, message)
            if self.log_listbox.size() > 10:
                self.log_listbox.delete(0)
            self.log_listbox.yview(tk.END)
        except tk.TclError:
            pass

    def run_task(self):
        try:
            collection.collect_news_cycle(
                urls=self.selected_rss,
                path=self.save_path,
                cancel_event=self.cancel_event,
                ui_callback=self.update_ui_log,
                file_logger=self.logger,
            )
        except Exception as exc:
            self._error = "수집 중 오류가 발생했습니다. crawler_error.log와 db/db.log를 확인해주세요."
            if self.logger:
                self.logger.exception("수집 중 예외가 발생했습니다: %s", exc)
        finally:
            self._close_logger()
            self._finished.set()

    def stop_crawling(self):
        """종료 버튼을 누르면 취소 신호를 보내고 진행 창을 닫습니다."""
        if self.is_collecting:
            self.cancel_event.set()
            if self.logger:
                self.logger.info("사용자가 수집 종료를 요청했습니다.")
        self._destroy_window()

    def on_finish(self):
        self.is_collecting = False
        self._destroy_window()

    def on_close(self):
        """창의 X 버튼도 수집 종료와 동일하게 처리합니다."""
        self.stop_crawling()

    def _close_logger(self):
        if not self.logger:
            return
        for handler in list(self.logger.handlers):
            self.logger.removeHandler(handler)
            handler.close()

    def _destroy_window(self):
        if self._closed:
            return
        self._closed = True
        try:
            self.window.destroy()
        except tk.TclError:
            pass
