"""환경 설정 화면."""
from PySide6.QtWidgets import QDialog, QFormLayout, QLineEdit, QSpinBox, QHBoxLayout, QFileDialog, QMessageBox, QCheckBox
from init import config
from gui_design import page_layout, button, configure_window, FORM_SPACING
from .setting import save_config, validate_db_settings

class DatabaseSettingWindow(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("환경 설정")
        configure_window(self, "settings")
        layout = page_layout(self, "환경 설정", "로컬 PostgreSQL 서버와 뉴스 저장 환경을 설정합니다.")
        form = QFormLayout()
        form.setSpacing(FORM_SPACING)
        self.fields = {}
        for key, label in [
            ("POSTGRES_BIN", "PostgreSQL bin 폴더"), ("SAVE_PATH", "서버 데이터 저장 폴더"),
            ("DB_HOST", "호스트"), ("DB_USER", "사용자"),
            ("DB_PASSWORD", "비밀번호"), ("DB_NAME", "데이터베이스"),
        ]:
            field = QLineEdit(str(getattr(config, key, "")))
            self.fields[key] = field
            if key in ("POSTGRES_BIN", "SAVE_PATH"):
                row = QHBoxLayout()
                row.addWidget(field, 1)
                row.addWidget(button("찾아보기", lambda checked=False, f=field: self.browse(f)))
                form.addRow(label, row)
            else:
                form.addRow(label, field)
        self.fields["DB_PASSWORD"].setEchoMode(QLineEdit.EchoMode.Password)
        show = QCheckBox("비밀번호 표시")
        show.toggled.connect(lambda value: self.fields["DB_PASSWORD"].setEchoMode(
            QLineEdit.EchoMode.Normal if value else QLineEdit.EchoMode.Password))
        form.addRow("", show)
        self.port = QSpinBox()
        self.port.setRange(1, 65535)
        self.port.setValue(int(getattr(config, "DB_PORT", 5432)))
        form.insertRow(3, "포트", self.port)
        layout.addLayout(form)
        layout.addStretch()
        row = QHBoxLayout()
        row.addStretch()
        row.addWidget(button("취소", self.reject))
        row.addWidget(button("설정 저장", self.save_config, "primary"))
        layout.addLayout(row)

    def browse(self, field):
        value = QFileDialog.getExistingDirectory(self, "폴더 선택", field.text())
        if value:
            field.setText(value)

    def save_config(self):
        settings = {key: field.text().strip() for key, field in self.fields.items()}
        settings["DB_PASSWORD"] = self.fields["DB_PASSWORD"].text()
        settings["DB_PORT"] = self.port.value()
        try:
            validate_db_settings(settings)
            save_config(settings)
        except Exception as exc:
            QMessageBox.warning(self, "설정 저장 실패", str(exc))
            return
        QMessageBox.information(self, "설정 저장", "설정을 저장했습니다.")
        self.accept()