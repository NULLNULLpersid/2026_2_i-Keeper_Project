"""수집·중단·재실행 상태와 실제 수집 백엔드를 연결한다."""
import logging
import tempfile
import threading
from datetime import datetime
from pathlib import Path
from uuid import uuid4
from PySide6.QtCore import QThread, Signal
from PySide6.QtWidgets import QDialog, QLabel, QProgressBar, QPlainTextEdit, QHBoxLayout, QMessageBox
from init import config
from gui_design import page_layout, button, configure_window, set_button_kind
from setting.setting import validate_db_settings
from .media_select.media_select import build_selected_feeds

def create_log_path():
    """실행별 로그 생성. 프로젝트에 쓰지 못하면 임시 폴더를 사용한다."""
    name = f"news_collection_{datetime.now():%Y%m%d_%H%M%S}_{uuid4().hex[:8]}.log"
    roots = [
        Path(__file__).resolve().parent.parent / "logs",
        Path(tempfile.gettempdir()) / "news_project_logs",
    ]
    for root in roots:
        try:
            root.mkdir(parents=True, exist_ok=True)
            path = root / name
            path.touch(exist_ok=False)
            return path
        except OSError:
            continue
    raise OSError("수집 오류 로그 파일을 생성할 수 없습니다.")

class CollectionWorker(QThread):
    message = Signal(str)

    def __init__(self, feeds, path, log_path, parent=None):
        super().__init__(parent)
        self.feeds = feeds
        self.path = path
        self.log_path = log_path
        self.cancel_event = threading.Event()
        self.error = None
        self.result = None

    def run(self):
        logger = logging.getLogger(f"CrawlerLogger-{id(self)}")
        logger.setLevel(logging.INFO)
        logger.propagate = False
        handler = None
        try:
            handler = logging.FileHandler(self.log_path, encoding="utf-8")
            handler.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(message)s"))
            logger.addHandler(handler)
            from .collection import collect_news_cycle
            logger.info("뉴스 수집 시작")
            self.message.emit("서버 연결 및 수집을 시작합니다.")
            self.result = collect_news_cycle(
                urls=self.feeds, path=self.path, cancel_event=self.cancel_event,
                ui_callback=self.message.emit, file_logger=logger)
            logger.info("수집 종료: 취소=%s 결과=%s", self.cancel_event.is_set(), self.result)
        except Exception:
            logger.exception("수집 중 오류")
            self.error = f"수집 중 오류가 발생했습니다. 오류 로그: {self.log_path}"
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
        self.log_path = None
        self.is_collecting = False
        self.close_when_finished = False
        layout = page_layout(self, "뉴스 수집", "RSS 조회 → 본문 수집 → PostgreSQL 저장")
        self.status = QLabel("수집 준비")
        self.status.setWordWrap(True)
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
        self.stop_button = button("수집 실행", self.toggle_collection, "success")
        self.close_button = button("닫기", self.request_close)
        row.addWidget(self.stop_button)
        row.addWidget(self.close_button)
        layout.addLayout(row)

    def start(self):
        if self.is_collecting:
            return True
        try:
            self.log_path = create_log_path()
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
            if self.log_path:
                try:
                    with self.log_path.open("a", encoding="utf-8") as stream:
                        stream.write(f"[ERROR] 수집 시작 불가: {exc}\n")
                    self.log.appendPlainText(f"오류 로그: {self.log_path}")
                except OSError as log_error:
                    self.log.appendPlainText(f"로그 기록 실패: {log_error}")
            QMessageBox.warning(self, "수집 시작 불가", str(exc))
            return False
        if self.worker:
            self.worker.deleteLater()
        self.worker = CollectionWorker(feeds, config.SAVE_PATH, self.log_path, self)
        self.worker.message.connect(self.log.appendPlainText)
        self.worker.finished.connect(self.on_finish)
        self.is_collecting = True
        self.close_when_finished = False
        self.log.appendPlainText(f"수집 실행 · 로그: {self.log_path}")
        self.status.setText(f"수집 중 · RSS 피드 {len(feeds)}개")
        self.progress.setRange(0, 0)
        self.stop_button.setText("수집 중단")
        set_button_kind(self.stop_button, "danger")
        self.stop_button.setEnabled(True)
        self.worker.start()
        return True

    def toggle_collection(self):
        if self.is_collecting:
            self.stop_crawling()
        else:
            self.start()

    def stop_crawling(self):
        """중단만 요청한다. 완료 후 같은 창에서 다시 실행할 수 있다."""
        if self.worker and self.worker.isRunning():
            self.worker.cancel_event.set()
            self.status.setText("중단 요청 · 서버 준비 및 연결 정리가 끝날 때까지 기다려주세요.")
            self.stop_button.setEnabled(False)

    def on_finish(self):
        self.is_collecting = False
        self.progress.setRange(0, 1)
        self.progress.setValue(1)
        self.stop_button.setText("수집 실행")
        set_button_kind(self.stop_button, "success")
        self.stop_button.setEnabled(True)
        if self.worker.error:
            self.status.setText("수집 실패 · 다시 실행할 수 있습니다.")
            self.log.appendPlainText(self.worker.error)
            QMessageBox.warning(self, "뉴스 수집 오류", self.worker.error)
        elif self.worker.cancel_event.is_set():
            self.status.setText("수집 중단 완료 · 다시 실행할 수 있습니다.")
            self.log.appendPlainText("수집을 중단했습니다.")
        else:
            failed = (self.worker.result or {}).get("failed", 0)
            self.status.setText(f"수집 완료 · 오류 {failed}건" if failed else "수집 완료")
            if failed:
                self.log.appendPlainText(f"오류 로그를 확인해주세요: {self.log_path}")
        if self.close_when_finished:
            super().reject()

    def request_close(self):
        if self.is_collecting:
            self.close_when_finished = True
            self.stop_crawling()
        else:
            super().reject()

    def reject(self):
        self.request_close()

    def closeEvent(self, event):
        if self.is_collecting:
            self.request_close()
            event.ignore()
        else:
            super().closeEvent(event)