"""수집 환경 확인"""
import importlib
from init import config
from setting.setting import postgres_binaries_exist

class LibraryManager:
    library_list = [
        ("PySide6", "PySide6"),
        ("aiohttp", "aiohttp"),
        ("asyncpg", "asyncpg"),
        ("pgvector", "pgvector"),
        ("feedparser", "feedparser"),
        ("trafilatura", "trafilatura"),
        ("numpy", "numpy"),
    ]

    @classmethod
    def missing_libraries(cls):
        missing = []
        for module, package in cls.library_list:
            try:
                importlib.import_module(module)
            except Exception:
                missing.append(package)
        return missing

    @classmethod
    def verification_libry(cls):
        return cls.missing_libraries()

def check_environment():
    missing = LibraryManager.missing_libraries()
    messages = []
    if missing:
        messages += ["누락 또는 로딩 실패: " + ", ".join(missing),
                     "python -m pip install -r requirements.txt로 설치해주세요."]
    else:
        messages.append("수집 라이브러리 확인 완료")
    if not postgres_binaries_exist(getattr(config, "POSTGRES_BIN", "")):
        messages.append("환경 설정에서 PostgreSQL bin 폴더를 지정해주세요.")
    else:
        messages.append("PostgreSQL 실행 파일 경로 확인 완료")
    messages.append("DB 연결과 pgvector 확장은 수집 시작 시 확인합니다.")
    return messages