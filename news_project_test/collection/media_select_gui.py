"""언론사 선택은 적용할 때만 저장한다."""
from PySide6.QtWidgets import QDialog, QTabWidget, QWidget, QVBoxLayout, QGridLayout, QScrollArea, QCheckBox, QHBoxLayout, QLabel, QMessageBox
from init import config
from style import page_layout, button, configure_window, MEDIA_COLUMNS
from .media_select import update_selected_media_config

class MediaSelectionWindow(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("수집할 언론사 선택")
        configure_window(self, "media_selection")
        layout = page_layout(self, "언론사 선택", "분류별 수집 대상을 선택하세요. 취소하면 기존 선택을 유지합니다.")
        self.checkboxes = {}
        tabs = QTabWidget()
        selected = set(getattr(config, "SELECTED_RSS", []))
        for category, publishers in config.MEDIA_RSS.items():
            page = QWidget()
            content = QVBoxLayout(page)
            items = {}
            content.addWidget(button("분류 전체 선택 / 해제", lambda checked=False, c=category: self.toggle_category(c)))
            scroll = QScrollArea()
            scroll.setWidgetResizable(True)
            container = QWidget()
            grid = QGridLayout(container)
            for index, name in enumerate(publishers):
                item = QCheckBox(name)
                item.setChecked(name in selected)
                item.toggled.connect(self.update_count)
                grid.addWidget(item, index // MEDIA_COLUMNS, index % MEDIA_COLUMNS)
                items[name] = item
            grid.setRowStretch((len(items) + MEDIA_COLUMNS - 1) // MEDIA_COLUMNS, 1)
            scroll.setWidget(container)
            content.addWidget(scroll)
            self.checkboxes[category] = items
            tabs.addTab(page, category)
        layout.addWidget(tabs, 1)
        self.count = QLabel()
        layout.addWidget(self.count)
        self.update_count()
        row = QHBoxLayout()
        row.addStretch()
        row.addWidget(button("취소", self.reject))
        row.addWidget(button("선택 완료", self.apply_and_close, "primary"))
        layout.addLayout(row)

    def selected_names(self):
        return [name for group in self.checkboxes.values() for name, item in group.items() if item.isChecked()]

    def update_count(self):
        if hasattr(self, "count"):
            self.count.setText(f"선택한 언론사: {len(self.selected_names())}개")

    def toggle_category(self, category):
        items = list(self.checkboxes[category].values())
        checked = not all(item.isChecked() for item in items)
        for item in items:
            item.setChecked(checked)

    def apply_and_close(self):
        try:
            update_selected_media_config(self.selected_names())
        except Exception as exc:
            QMessageBox.warning(self, "저장 실패", str(exc))
            return
        self.accept()