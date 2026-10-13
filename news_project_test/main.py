"""PySide6 프로그램 실행 진입점."""
import sys

def main():
    from init.init import initialize
    try:
        initialize()
    except Exception as exc:
        print(f"[초기화 실패] {exc}", file=sys.stderr)
        return 1

    # PySide6 자동 설치와 import 검증이 끝난 뒤 GUI를 가져온다.
    from PySide6.QtWidgets import QApplication
    from gui_design import apply_theme
    from main_gui import NewsApp
    from init.init_gui import EnvChecker
    app = QApplication(sys.argv)
    app.setApplicationName("뉴스기사 수집 및 분석")
    apply_theme(app)
    window = NewsApp()
    checker = EnvChecker(window, on_complete_callback=window.show)
    checker.show()
    try:
        return app.exec()
    finally:
        # 모든 수집 스레드와 DB 연결 정리가 끝난 뒤 서버 종료.
        from PySide6.QtCore import QThread
        for worker in window.findChildren(QThread):
            if worker.isRunning():
                if hasattr(worker, "cancel_event"):
                    worker.cancel_event.set()
                worker.wait()
        from db.setting import shutdown_registered_servers
        shutdown_registered_servers()

if __name__ == "__main__":
    raise SystemExit(main())