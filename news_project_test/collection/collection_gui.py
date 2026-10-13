"""수집 백엔드와 Qt 시그널을 연결하는 진행 화면."""
import logging
import os
import threading
from pathlib import Path
from PySide6.QtCore import QThread, Signal
from PySide6.QtWidgets import QDialog, QLabel, QProgressBar, QPlainTextEdit, QHBoxLayout, QMessageBox
from init import config
from gui_design import page_layout, button, configure_window
from setting.setting import validate_db_settings
from .media_select.media_select import build_selected_feeds

class CollectionWorker(QThread):
    message = Signal(str)

    def __init__(self, feeds, path, parent=None):
        super().__init__(parent)
        self.feeds = feeds
        self.path = path
        self.cancel_event = threading.Event()
        self.error = None
        self.result = None

    def run(self):
        logger = logging.getLogger(f"CrawlerLogger-{id(self)}")
        logger.setLevel(logging.INFO)
        logger.propagate = False
        handler = None
        try:
            os.makedirs(self.path, exist_ok=True)
            handler = logging.FileHandler(Path(self.path) / "crawler_error.log", encoding="utf-8")
            handler.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(message)s"))
            logger.addHandler(handler)
            # 의존성과 DB 모듈은 실제 작업 시점에 가져온다.
            from .collection import collect_news_cycle
            self.message.emit("서버 연결 및 수집을 시작합니다.")
            self.result = collect_news_cycle(
                urls=self.feeds, path=self.path, cancel_event=self.cancel_event,
                ui_callback=self.message.emit, file_logger=logger)
        except Exception:
            logger.exception("수집 중 오류")
            self.error = "수집 중 오류가 발생했습니다. crawler_error.log와 db/db.log를 확인해주세요."
        finally:
            if handler:
                logger.removeHandler(handler)
                handler.close()

class CrawlerProgressWindow(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("뉴스 수집 진행")
        configure_window(self, "collection_progress")
        self.worker = None
        self.is_collecting = False
        self.close_when_finished = False
        layout = page_layout(self, "뉴스 수집", "RSS 조회 → 본문 수집 → PostgreSQL 저장")
        self.status = QLabel("수집 준비")
        layout.addWidget(self.status)
        self.progress = QProgressBar()
        self.progress.setRange(0, 1)
        self.progress.setValue(0)
        layout.addWidget(self.progress)
        self.log = QPlainTextEdit()
        self.log.setReadOnly(True)
        self.log.setMaximumBlockCount(1500)
        layout.addWidget(self.log, 1)
        row = QHBoxLayout()
        row.addStretch()
        self.stop_button = button("수집 중단", self.stop_crawling, "danger")
        row.addWidget(self.stop_button)
        layout.addLayout(row)

    def start(self):
        """유효성 검사 후 실제 수집을 시작. 실패하면 창을 표시하지 않는다."""
        if self.is_collecting:
            return True
        try:
            feeds = build_selected_feeds(config.MEDIA_RSS, getattr(config, "SELECTED_RSS", []))
            if not feeds:
                raise ValueError("수집할 언론사를 먼저 선택해주세요.")
            from .crawler.media_rss_reader import get_reader
            for feed in feeds:
                get_reader(feed["media_name"])
            validate_db_settings({key: getattr(config, key, "") for key in
                ("DB_HOST", "DB_PORT", "DB_USER", "DB_PASSWORD", "DB_NAME",
                 "POSTGRES_BIN", "SAVE_PATH")})
        except Exception as exc:
            QMessageBox.warning(self.parentWidget(), "수집 시작 불가", str(exc))
            return False
        self.worker = CollectionWorker(feeds, config.SAVE_PATH, self)
        self.worker.message.connect(self.log.appendPlainText)
        self.worker.finished.connect(self.on_finish)
        self.is_collecting = True
        self.status.setText(f"수집 중 · RSS 피드 {len(feeds)}개")
        self.progress.setRange(0, 0)
        self.worker.start()
        return True

    def stop_crawling(self):
        if self.worker and self.worker.isRunning():
            self.close_when_finished = True
            self.worker.cancel_event.set()
            self.status.setText("중단 요청 · 서버 준비 및 연결 정리가 끝날 때까지 기다려주세요.")
            self.stop_button.setEnabled(False)
            return
        super().reject()

    def on_finish(self):
        self.is_collecting = False
        self.progress.setRange(0, 1)
        self.progress.setValue(1)
        if self.worker.error:
            self.status.setText("수집 실패")
            self.log.appendPlainText(self.worker.error)
            QMessageBox.warning(self, "뉴스 수집 오류", self.worker.error)
            self.stop_button.setText("닫기")
            self.stop_button.setEnabled(True)
            if self.close_when_finished:
                self.close()
            return
        self.status.setText("수집 중단 완료" if self.worker.cancel_event.is_set() else "수집 완료")
        # 성공 또는 중단 시 기존 설계대로 진행 창을 닫는다.
        self.close()

    def reject(self):
        # Esc 키도 X/중단 버튼과 같은 수명주기를 따른다.
        self.stop_crawling()

    def closeEvent(self, event):
        if self.worker and self.worker.isRunning():
            self.stop_crawling()
            event.ignore()
        else:
            super().closeEvent(event)