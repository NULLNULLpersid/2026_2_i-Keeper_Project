"""메인 화면과 뉴스 수집 메뉴."""
from PySide6.QtWidgets import QMainWindow, QWidget, QFrame, QLabel
from init import config
from style import page_layout, button, configure_window, card_layout
from setting.setting_gui import DatabaseSettingWindow

from collection.collection_menu_gui import CollectionMenu

class NewsApp(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("뉴스기사 수집 및 분석")
        configure_window(self, "main")
        self.collection_menu = None
        self.settings_window = None
        widget = QWidget()
        self.setCentralWidget(widget)
        layout = page_layout(widget, "뉴스 기사 수집 및 분석", "RSS기반 뉴스 수집 및 분석")
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

    def open_settings(self):
        if self.settings_window is None:
            self.settings_window = DatabaseSettingWindow(self)
            self.settings_window.finished.connect(self.on_settings_closed)
        self.settings_window.show()
        self.settings_window.raise_()
        self.settings_window.activateWindow()

    def on_settings_closed(self):
        dialog = self.settings_window
        self.settings_window = None
        if dialog:
            dialog.deleteLater()

    def open_collection_menu(self):
        # exec()의 중첩 이벤트 루프는 hide()로 종료될 수 있으므로 사용하지 않는다.
        if self.collection_menu is None:
            self.collection_menu = CollectionMenu(self)
            self.collection_menu.setModal(False)
        progress = self.collection_menu.worker_window
        target = progress if progress is not None else self.collection_menu
        target.show()
        target.raise_()
        target.activateWindow()

    def closeEvent(self, event):
        from collection.collection_progress_gui import CollectionWorker
        workers = [w for w in self.findChildren(CollectionWorker) if w.isRunning()]
        if workers:
            for worker in workers:
                worker.cancel_event.set()
            event.ignore()
            return
        super().closeEvent(event)
