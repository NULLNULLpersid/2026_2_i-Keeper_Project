import tkinter as tk
from tkinter import filedialog, messagebox

import config
from setting import setting

FONT_NORMAL = ("Helvetica", 10)
FONT_BUTTON = ("Helvetica", 10, "bold")
WINDOW_SIZE = "400x500"
MSG_ERROR_TITLE = "오류"
MSG_SAVE_TITLE = "설정 저장"
MSG_SAVE_SUCCESS = "데이터베이스 설정이 성공적으로 변경 및 저장되었습니다."
MSG_SAVE_FAILED = "설정을 저장하는 중 오류가 발생했습니다:"
LABEL_PG_BIN = "PostgreSQL Bin 경로:"
LABEL_DB_HOST = "DB Host:"
LABEL_DB_PORT = "DB Port:"
LABEL_DB_USER = "DB User:"
LABEL_DB_PASSWORD = "DB Password:"
LABEL_SAVE_PATH = "서버 저장 폴더 위치:"


def create_small_button(parent, text, command):
    return tk.Button(parent, text=text, font=("Helvetica", 9, "bold"), command=command)


def create_standard_button(parent, text, command):
    return tk.Button(parent, text=text, width=35, height=2, font=FONT_BUTTON, command=command)

class DatabaseSettingWindow:
    def __init__(self, parent_root):
        self.parent = parent_root
        
        self.window = tk.Toplevel(self.parent)
        self.window.title("데이터베이스 및 SQL 설정")
        self.window.geometry(WINDOW_SIZE)
        self.parent.eval(f'tk::PlaceWindow {str(self.window)} center')

        # 입력 필드 변수 초기화 (전역 주입된 config 활용)
        self.bin_var = tk.StringVar(value=getattr(config, 'POSTGRES_BIN', ""))
        self.host_var = tk.StringVar(value=getattr(config, 'DB_HOST', "127.0.0.1"))
        self.port_var = tk.StringVar(value=str(getattr(config, 'DB_PORT', 5432)))
        self.user_var = tk.StringVar(value=getattr(config, 'DB_USER', "postgres"))
        self.password_var = tk.StringVar(value=getattr(config, 'DB_PASSWORD', "postgres"))
        self.save_path_var = tk.StringVar(value=getattr(config, 'SAVE_PATH', ""))

        self.setup_ui()

    def setup_ui(self):
        main_frame = tk.Frame(self.window, padx=20, pady=20)
        main_frame.pack(fill="both", expand=True)

        # 1. PostgreSQL Bin 경로
        row = 0
        tk.Label(main_frame, text=LABEL_PG_BIN, font=FONT_NORMAL).grid(row=row, column=0, sticky="w", pady=5)
        bin_frame = tk.Frame(main_frame)
        bin_frame.grid(row=row+1, column=0, columnspan=2, sticky="ew", pady=2)
        tk.Entry(bin_frame, textvariable=self.bin_var, width=32, font=FONT_NORMAL).pack(side="left", padx=(0, 5))
        create_small_button(bin_frame, "찾아보기", self.select_pg_directory).pack(side="left")

        # 2. Host
        row = 2
        tk.Label(main_frame, text=LABEL_DB_HOST, font=FONT_NORMAL).grid(row=row, column=0, sticky="w", pady=(10, 2))
        tk.Entry(main_frame, textvariable=self.host_var, width=30, font=FONT_NORMAL).grid(row=row+1, column=0, sticky="w", pady=2)

        # 3. Port
        row = 4
        tk.Label(main_frame, text=LABEL_DB_PORT, font=FONT_NORMAL).grid(row=row, column=0, sticky="w", pady=(10, 2))
        tk.Entry(main_frame, textvariable=self.port_var, width=30, font=FONT_NORMAL).grid(row=row+1, column=0, sticky="w", pady=2)

        # 4. User
        row = 6
        tk.Label(main_frame, text=LABEL_DB_USER, font=FONT_NORMAL).grid(row=row, column=0, sticky="w", pady=(10, 2))
        tk.Entry(main_frame, textvariable=self.user_var, width=30, font=FONT_NORMAL).grid(row=row+1, column=0, sticky="w", pady=2)

        # 5. Password
        row = 8
        tk.Label(main_frame, text=LABEL_DB_PASSWORD, font=FONT_NORMAL).grid(row=row, column=0, sticky="w", pady=(10, 2))
        tk.Entry(main_frame, textvariable=self.password_var, show="*", width=30, font=FONT_NORMAL).grid(row=row+1, column=0, sticky="w", pady=2)

        # 6. 데이터 저장 폴더
        row = 10
        tk.Label(main_frame, text=LABEL_SAVE_PATH, font=FONT_NORMAL).grid(row=row, column=0, sticky="w", pady=(15, 2))
        path_frame = tk.Frame(main_frame)
        path_frame.grid(row=row+1, column=0, columnspan=2, sticky="ew", pady=2)
        tk.Entry(path_frame, textvariable=self.save_path_var, width=32, font=FONT_NORMAL).pack(side="left", padx=(0, 5))
        create_small_button(path_frame, "찾아보기", self.select_save_directory).pack(side="left")

        # 저장 버튼
        save_btn = create_standard_button(main_frame, text="저장", command=self.save_config)
        save_btn.grid(row=13, column=0, columnspan=2, pady=(25, 0))

    def select_pg_directory(self):
        folder_selected = filedialog.askdirectory()
        if folder_selected:
            self.bin_var.set(folder_selected)

    def select_save_directory(self):
        folder_selected = filedialog.askdirectory()
        if folder_selected:
            self.save_path_var.set(folder_selected)

    def save_config(self):
        try:
            port_val = int(self.port_var.get())
        except ValueError:
            messagebox.showerror(MSG_ERROR_TITLE, "Port 번호는 숫자여야 합니다.")
            return

        new_settings = {
            "POSTGRES_BIN": self.bin_var.get(),
            "DB_HOST": self.host_var.get(),
            "DB_PORT": port_val,
            "DB_USER": self.user_var.get(),
            "DB_PASSWORD": self.password_var.get(),
            "SAVE_PATH": self.save_path_var.get()
        }

        try:
            setting.save_db_config(new_settings)
            messagebox.showinfo(MSG_SAVE_TITLE, MSG_SAVE_SUCCESS)
            self.window.destroy()

        except Exception as e:
            messagebox.showerror(MSG_ERROR_TITLE, f"{MSG_SAVE_FAILED} {e}")
