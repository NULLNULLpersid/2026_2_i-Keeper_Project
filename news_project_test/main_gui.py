"""메인 화면과 뉴스 수집 메뉴."""
from PySide6.QtWidgets import QMainWindow, QWidget, QDialog, QFrame, QLabel
from init import config
from gui_design import page_layout, button, configure_window, card_layout
from setting.setting_gui import DatabaseSettingWindow
from collection.media_select.media_select_gui import MediaSelectionWindow
from collection.collection_gui import CrawlerProgressWindow

class CollectionMenu(QDialog):
    def __init__(self, parent):
        super().__init__(parent)
        self.setWindowTitle("뉴스 수집")
        configure_window(self, "collection_menu")
        self.worker_window = None
        layout = page_layout(self, "뉴스 수집", "언론사를 선택하고 RSS 뉴스 수집을 시작하세요.")
        self.summary = QLabel()
        layout.addWidget(self.summary)
        layout.addWidget(button("언론사 선택", self.select_media))
        layout.addWidget(button("뉴스 수집 시작", self.start_collection, "primary"))
        layout.addStretch()
        layout.addWidget(button("닫기", self.close))
        self.refresh_summary()

    def refresh_summary(self):
        names = list(getattr(config, "SELECTED_RSS", []))
        self.summary.setText(f"선택한 언론사 {len(names)}개\n" + (", ".join(names) or "언론사를 선택해주세요."))
        self.summary.setWordWrap(True)

    def select_media(self):
        MediaSelectionWindow(self).exec()
        self.refresh_summary()

    def start_collection(self):
        if self.worker_window and self.worker_window.isVisible():
            self.worker_window.raise_()
            self.worker_window.activateWindow()
            return
        dialog = CrawlerProgressWindow(self)
        if dialog.start():
            self.worker_window = dialog
            dialog.setModal(True)
            dialog.show()

    def reject(self):
        if self.worker_window and self.worker_window.is_collecting:
            self.worker_window.stop_crawling()
            return
        super().reject()

    def closeEvent(self, event):
        if self.worker_window and self.worker_window.is_collecting:
            self.worker_window.stop_crawling()
            event.ignore()
            return
        super().closeEvent(event)

class NewsApp(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("뉴스기사 수집 및 분석")
        configure_window(self, "main")
        widget = QWidget()
        self.setCentralWidget(widget)
        layout = page_layout(widget, "뉴스 기사 수집 및 분석", "RSS 기반 뉴스 수집 · PostgreSQL 데이터 관리")
        card = QFrame()
        content = card_layout(card)
        content.addWidget(QLabel("작업을 선택하세요"))
        content.addWidget(button("환경 설정", self.open_settings))
        content.addWidget(button("뉴스 수집하러가기", self.open_collection_menu, "primary"))
        analysis = button("뉴스 분석하러가기 · 준비 중")
        analysis.setEnabled(False)
        content.addWidget(analysis)
        layout.addWidget(card)
        layout.addStretch()
        layout.addWidget(QLabel("i-Keeper  |  뉴스 수집 프로젝트"))

    def open_settings(self):
        DatabaseSettingWindow(self).exec()

    def open_collection_menu(self):
        CollectionMenu(self).exec()

    def closeEvent(self, event):
        from collection.collection_gui import CollectionWorker
        workers = [w for w in self.findChildren(CollectionWorker) if w.isRunning()]
        if workers:
            for worker in workers:
                worker.cancel_event.set()
            event.ignore()
            return
        super().closeEvent(event)