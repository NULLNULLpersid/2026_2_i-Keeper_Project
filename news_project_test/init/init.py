"""프로그램 시작 초기화. 설치 구현은 library_install.py가 담당한다."""
from init import config
from .library_install import prepare_libraries
from setting.setting import postgres_binaries_exist, save_config


def initialize(report=print):
    """Qt를 포함한 모든 필수 패키지를 GUI import 전에 준비한다."""
    installed = prepare_libraries(report)
    if getattr(config, "INSTALLED_LIBRARIES", []) != installed:
        try:
            save_config({"INSTALLED_LIBRARIES": installed})
        except OSError as exc:
            # 설치 기록 저장 실패는 실제 설치 성공을 무효화하지 않는다.
            report(f"[안내] 설치 목록 저장 실패: {exc}")
    return installed


def check_environment():
    """설치 완료 후 환경 확인 화면에 표시할 정보를 반환한다."""
    messages = ["필수 라이브러리 준비 완료"]
    if not postgres_binaries_exist(getattr(config, "POSTGRES_BIN", "")):
        messages.append("환경 설정에서 PostgreSQL bin 폴더를 지정해주세요.")
    else:
        messages.append("PostgreSQL 실행 파일 경로 확인 완료")
    messages.append("DB 연결과 pgvector 확장은 수집 시작 시 확인합니다.")
    return messages