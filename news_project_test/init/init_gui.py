"""환경 검사 작업과 PySide6 시작 화면."""
from PySide6.QtCore import QThread, Signal
from PySide6.QtWidgets import QDialog, QPlainTextEdit, QProgressBar
from gui_common import page_layout, button
from .init import check_environment

class EnvironmentWorker(QThread):
    messages = Signal(list)
    def run(self):
        try:
            self.messages.emit(check_environment())
        except Exception as exc:
            self.messages.emit([f"환경 확인 실패: {exc}"])

class EnvChecker(QDialog):
    def __init__(self, root=None, on_complete_callback=None):
        super().__init__(root)
        self.on_complete = on_complete_callback
        self.setWindowTitle("초기 환경 확인")
        self.resize(660, 390)
        layout = page_layout(self, "환경 확인", "라이브러리와 PostgreSQL 경로를 확인합니다.")
        self.log = QPlainTextEdit()
        self.log.setReadOnly(True)
        layout.addWidget(self.log)
        self.progress = QProgressBar()
        self.progress.setRange(0, 0)
        layout.addWidget(self.progress)
        self.continue_button = button("메인 화면으로", self.complete, "primary")
        self.continue_button.setEnabled(False)
        layout.addWidget(self.continue_button)
        self.worker = EnvironmentWorker(self)
        self.worker.messages.connect(self.show_messages)
        self.worker.finished.connect(self.checked)
        self.worker.start()

    def show_messages(self, messages):
        self.log.setPlainText("\n".join(messages))

    def checked(self):
        self.progress.setRange(0, 1)
        self.progress.setValue(1)
        self.continue_button.setEnabled(True)

    def complete(self):
        if self.worker.isRunning():
            return
        if self.on_complete:
            self.on_complete()
        self.accept()

    def reject(self):
        if not self.worker.isRunning():
            super().reject()

    def closeEvent(self, event):
        if self.worker.isRunning():
            event.ignore()
        else:
            super().closeEvent(event)
