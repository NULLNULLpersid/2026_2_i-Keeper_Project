"""인터페이스·서버 경로·서버 접속 설정 화면."""
from PySide6.QtWidgets import (
    QApplication, QDialog, QLabel, QFormLayout, QLineEdit, QHBoxLayout,
    QGridLayout, QGroupBox, QButtonGroup, QFileDialog, QMessageBox, QCheckBox, QRadioButton,
)
from init import config
from gui_design import page_layout, button, configure_window, FORM_SPACING, apply_theme
from .setting import save_config, validate_db_settings

class DatabaseSettingWindow(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("환경 설정")
        configure_window(self, "settings")
        layout = page_layout(
            self, "환경 설정",
            "로컬 서버의 정보와 뉴스 저장 환경을 설정합니다.\n"
            "설정을 변경 후 꼭 저장을 눌러주세요.",
        )
        self.fields = {}
        grid = QGridLayout()
        interface = QGroupBox("인터페이스 설정")
        theme_row = QHBoxLayout(interface)
        self.dark_radio = QRadioButton("검정색")
        self.light_radio = QRadioButton("흰색")
        self.dark_radio.setChecked(getattr(config, "UI_THEME", "light") == "dark")
        self.light_radio.setChecked(not self.dark_radio.isChecked())
        self.theme_group = QButtonGroup(self)
        self.theme_group.addButton(self.dark_radio)
        self.theme_group.addButton(self.light_radio)
        self.theme_group.setExclusive(True)
        theme_row.addWidget(self.dark_radio)
        theme_row.addWidget(self.light_radio)
        theme_row.addStretch()
        grid.addWidget(interface, 0, 0)

        server = QGroupBox("서버 설정")
        server_form = QFormLayout(server)
        server_form.setSpacing(FORM_SPACING)
        for key, label in [
            ("POSTGRES_BIN", "데이터베이스 /bin 폴더 경로"),
            ("SAVE_PATH", "데이터 저장 폴더 경로"),
        ]:
            field = QLineEdit(str(getattr(config, key, "")))
            self.fields[key] = field
            row = QHBoxLayout()
            row.addWidget(field, 1)
            row.addWidget(button("찾아보기", lambda checked=False, f=field: self.browse(f)))
            server_form.addRow(QLabel(label))
            server_form.addRow(row)
        grid.addWidget(server, 1, 0)

        connection = QGroupBox("서버 접속 설정")
        connection_form = QFormLayout(connection)
        connection_form.setSpacing(FORM_SPACING)
        for key, label in [
            ("DB_HOST", "호스트"), ("DB_PORT", "포트"),
            ("DB_USER", "사용자"), ("DB_PASSWORD", "비밀번호"),
        ]:
            field = QLineEdit(str(getattr(config, key, "")))
            self.fields[key] = field
            connection_form.addRow(label, field)
        self.initial_db_values = {key: field.text() for key, field in self.fields.items()}
        self.port = self.fields["DB_PORT"]
        self.fields["DB_PASSWORD"].setEchoMode(QLineEdit.EchoMode.Password)
        self.show_password = QCheckBox("비밀번호 표시")
        self.show_password.toggled.connect(lambda visible: self.fields["DB_PASSWORD"].setEchoMode(
            QLineEdit.EchoMode.Normal if visible else QLineEdit.EchoMode.Password))
        connection_form.addRow("", self.show_password)
        grid.addWidget(connection, 0, 1, 2, 1)
        grid.setColumnStretch(0, 1)
        grid.setColumnStretch(1, 1)
        grid.setRowStretch(1, 1)
        layout.addLayout(grid, 1)
        row = QHBoxLayout()
        row.addStretch()
        row.addWidget(button("취소", self.reject))
        row.addWidget(button("저장", self.save_config, "primary"))
        layout.addLayout(row)

    def browse(self, field):
        value = QFileDialog.getExistingDirectory(self, "폴더 선택", field.text())
        if value:
            field.setText(value)

    def save_config(self):
        theme = "dark" if self.dark_radio.isChecked() else "light"
        # 인터페이스만 변경하면 기존 DB 경로의 유효성이 테마 저장을 막지 않는다.
        db_changed = any(field.text() != self.initial_db_values[key]
                         for key, field in self.fields.items())
        settings = {"UI_THEME": theme}
        try:
            if db_changed:
                database = {key: field.text().strip() for key, field in self.fields.items()}
                database["DB_PASSWORD"] = self.fields["DB_PASSWORD"].text()
                database["DB_NAME"] = getattr(config, "DB_NAME", "News_Data_Server")
                try:
                    database["DB_PORT"] = int(database["DB_PORT"])
                except ValueError:
                    raise ValueError("포트는 1~65535 사이의 숫자로 입력해주세요.") from None
                validate_db_settings(database)
                settings.update(database)
            save_config(settings)
        except Exception as exc:
            QMessageBox.warning(self, "설정 저장 실패", str(exc))
            return
        apply_theme(QApplication.instance(), theme)
        QMessageBox.information(self, "설정 저장", "설정을 저장했습니다.")
        self.accept()