"""GUI import 이전의 라이브러리 확인·자동 설치. 표준 라이브러리만 사용한다."""
import importlib
import site
import subprocess
import sys

# (검증할 import 이름, pip 패키지 이름)
LIBRARY_LIST = [
    ("PySide6.QtWidgets", "PySide6"),
    ("aiohttp", "aiohttp"),
    ("asyncpg", "asyncpg"),
    ("pgvector", "pgvector"),
    ("feedparser", "feedparser"),
    ("trafilatura", "trafilatura"),
    ("numpy", "numpy"),
    ("kiwipiepy", "kiwipiepy")
]


class LibraryInstallationError(RuntimeError):
    """설치 또는 설치 후 import 검증 실패."""


def ensure_library(module_name, package_name, report=print):
    try:
        importlib.import_module(module_name)
    except ModuleNotFoundError:
        if getattr(sys, "frozen", False):
            raise LibraryInstallationError(
                f"배포본에 {package_name}가 누락되어 있습니다. 패키징 구성을 확인해주세요."
            ) from None
        report(f"[설치 중] {package_name}")
        try:
            subprocess.run(
                [sys.executable, "-m", "pip", "install", package_name],
                check=True,
            )
            # 최초 user-site 설치 시 현재 프로세스에도 새 경로를 반영한다.
            if site.ENABLE_USER_SITE:
                site.addsitedir(site.getusersitepackages())
            importlib.invalidate_caches()
            importlib.import_module(module_name)
        except Exception as exc:
            raise LibraryInstallationError(
                f"{package_name} 자동 설치 또는 설치 후 확인에 실패했습니다: {exc}"
            ) from exc
    except Exception as exc:
        raise LibraryInstallationError(
            f"{package_name} 로딩에 실패했습니다: {exc}"
        ) from exc
    report(f"[확인 완료] {package_name}")
    return module_name.split(".")[0]


def prepare_libraries(report=print):
    """누락 패키지만 설치하고 실제 import에 성공한 목록을 반환한다."""
    return [ensure_library(module, package, report) for module, package in LIBRARY_LIST]