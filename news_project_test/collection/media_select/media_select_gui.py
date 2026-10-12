import tkinter as tk
from tkinter import ttk

import config
from . import media_select

WINDOW_SIZE = "750x550"
FONT_NORMAL = ("Helvetica", 10)
FONT_BUTTON = ("Helvetica", 10, "bold")


def create_button(parent, text, command):
    return tk.Button(parent, text=text, width=35, height=2, font=FONT_BUTTON, command=command)

class MediaSelectionWindow:
    def __init__(self, parent_root, check_vars, toggle_states):
        self.parent = parent_root
        self.check_vars = check_vars
        self.toggle_states = toggle_states

        # 취소 시 원복을 위한 백업
        self.backup_states = {
            category: {media_name: var.get() for media_name, var in media_vars.items()}
            for category, media_vars in self.check_vars.items()
        }
        self.backup_toggle_states = self.toggle_states.copy()

        # 서브 창 생성
        self.window = tk.Toplevel(self.parent)
        self.window.title("수집할 언론사 선택")
        self.window.geometry(WINDOW_SIZE)
        self.parent.eval(f'tk::PlaceWindow {str(self.window)} center')
        
        self.setup_ui()

    def setup_ui(self):
        notebook = ttk.Notebook(self.window)
        notebook.pack(fill="both", expand=True, padx=15, pady=15)

        # config.py에서 읽은 MEDIA_RSS 설정을 사용
        for category, media_list in config.MEDIA_RSS.items():
            tab_frame = tk.Frame(notebook)
            notebook.add(tab_frame, text=category)

            # 토글 버튼 (MediaLogic 호출)
            btn_toggle = tk.Button(
                tab_frame,
                text="모두 체크 / 해제",
                font=("Helvetica", 9, "bold"),
                command=lambda cat=category: media_select.toggle_category(self.check_vars, self.toggle_states, cat)
            )
            btn_toggle.pack(anchor="w", padx=10, pady=10)

            grid_frame = tk.Frame(tab_frame)
            grid_frame.pack(fill="both", expand=True, padx=10)

            col, row = 0, 0
            for media_name in media_list.keys():
                tk.Checkbutton(
                    grid_frame, 
                    text=media_name, 
                    variable=self.check_vars[category][media_name],
                    font=FONT_NORMAL
                ).grid(row=row, column=col, sticky="w", padx=5, pady=5)
                
                col += 1
                if col > 4:
                    col = 0
                    row += 1

        # 적용 버튼 (apply_and_close 호출)
        apply_btn = create_button(
            self.window,
            text="선택 완료",
            command=self.apply_and_close,
        )
        apply_btn.pack(pady=15)
        
        # X 버튼 닫기 이벤트 연결
        self.window.protocol("WM_DELETE_WINDOW", self.cancel_and_close)

    def apply_and_close(self):
        """로직 모듈을 이용해 데이터를 추출하고 파일에 저장한 뒤 창을 닫습니다."""
        selected_media_names = media_select.get_selected_media(self.check_vars)
        media_select.update_selected_media_config(selected_media_names)
        self.window.destroy()

    def cancel_and_close(self):
        """저장하지 않고 백업 데이터로 원복한 뒤 창을 닫습니다."""
        for cat, media_vars in self.check_vars.items():
            for media_name, var in media_vars.items():
                var.set(self.backup_states[cat][media_name])
                
        for cat, state in self.backup_toggle_states.items():
            self.toggle_states[cat] = state
            
        self.window.destroy()
