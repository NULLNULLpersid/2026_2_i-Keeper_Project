import builtins
import os
import tkinter as tk
from tkinter import messagebox

from init import config, reload_config as reload_project_config
from init import init
from init.init_gui import EnvChecker
from main_gui import NewsApp

# NSTALLED_LIBRARIES가 비어있는지 확인하여 '최초 실행 여부'를 전역 변수로 저장
IS_FIRST_RUN = not bool(getattr(config, 'INSTALLED_LIBRARIES', []))
APP_TITLE = "뉴스기사 수집 및 분석"
ERROR_TITLE = "오류"

def reload_config():
    """
    config.py의 최신 내용을 다시 읽어오는 함수
    """
    try:
        reload_project_config()
        builtins.config = config

        print("[CONFIG] config.py Reload 완료")

        return True

    except Exception as e:
        messagebox.showerror(
            ERROR_TITLE,
            f"config.py를 불러오는 중 오류가 발생했습니다.\n\n{e}"
        )

        return False

def is_postgres_configured():
    """
    config.py에 저장된 PostgreSQL 경로가 정상적인지 확인하는 함수
    
    검사:
        1. POSTGRES_BIN 값이 존재하는가?
        2. 해당 경로가 실제로 존재하는가?
        3. 해당 경로가 디렉터리인가?
    """
    
    path = getattr(config, "POSTGRES_BIN", "")
    if not path:
        return False
    norm_path = os.path.normpath(path)
    if not os.path.exists(norm_path) or not os.path.isdir(norm_path):
        return False
    if os.path.basename(norm_path).lower() != 'bin':
        return False
    return True

def launch_main_app(root):
    """
    메인 GUI를 실행하는 함수
    """

    # config.py 최신 내용 반영
    if not reload_config():
        return

    print("=" * 60)
    print("[MAIN] 메인 프로그램 시작")
    print(f"[MAIN] PostgreSQL 경로: {getattr(config, 'POSTGRES_BIN', '미설정')}")
    print("=" * 60)

    # 메인 창 표시
    root.deiconify()

    # 메인 GUI 생성
    root.app = NewsApp(root)

def check_postgres_and_launch(root):
    """환경 검사 이후에 호출되어 PostgreSQL 경로를 검사하고 메인 앱을 실행합니다."""
    # 최초 실행이 아니라면 저장된 경로가 유효한지 검사
    if not IS_FIRST_RUN:
        if not is_postgres_configured():
            messagebox.showwarning(
                "PostgreSQL 경로 오류", 
                "저장된 PostgreSQL 경로가 올바르지 않습니다.\n프로그램 내 '2단계: 경로 설정'에서 올바른 bin 폴더를 다시 지정해주세요."
            )
    launch_main_app(root)

# --------------------------------------------------
# 프로그램 시작
# --------------------------------------------------
def main():
    """
    프로그램 전체 시작 흐름
    """

    root = None
    try:
        # 초기화 실패나 중간 return도 아래 finally에서 정리한다.
        root = tk.Tk()
        root.withdraw()
        root.title(APP_TITLE)

        if not reload_config():
            return

        root.setup_app = EnvChecker(
            root,
            on_complete_callback=lambda: check_postgres_and_launch(root)
        )
        root.mainloop()

    except KeyboardInterrupt:
        print("\n[MAIN] 프로그램 종료 요청")

    except Exception as e:
        print(f"[MAIN] 프로그램 실행 중 오류: {e}")

    finally:
        # mainloop.quit() 경로에서도 남아 있는 GUI 자원을 먼저 정리한다.
        if root is not None:
            try:
                root.destroy()
            except tk.TclError:
                pass  # X 버튼으로 이미 파괴된 창
        try:
            # 지연 import: 초기 환경 검사 이전에 DB 모듈을 불러오지 않는다.
            from db.setting import shutdown_registered_servers
            shutdown_registered_servers()
        except Exception as e:
            print(f"[MAIN] 서버 종료 처리 중 오류: {e}")
        print("[MAIN] 프로그램 종료")

# Entry Point
if __name__ == "__main__":
    main()