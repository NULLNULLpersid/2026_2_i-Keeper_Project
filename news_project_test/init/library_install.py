"""누락 패키지 설치와 현재 Python 환경의 패키지 업데이트 자동화."""
from __future__ import annotations

import ast
import importlib
import json
import importlib.util
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile

from init import config, CONFIG_PATH


class LibraryInstallError(RuntimeError):
    """pip 실행 또는 업데이트 후 검증 실패."""


def _run(arguments, report=print, *, capture=False):
    """셸 없이 현재 Python을 실행한다. 설치 출력은 GUI 로그로 전달한다."""
    environment = os.environ.copy()
    environment["PYTHONIOENCODING"] = "utf-8"
    environment["PYTHONUNBUFFERED"] = "1"
    output = []
    try:
        with subprocess.Popen(
            [sys.executable, *arguments], stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            text=True, encoding="utf-8", errors="replace", env=environment,
        ) as process:
            for line in process.stdout:
                if capture:
                    output.append(line)
                else:
                    report(line.rstrip("\r\n"))
            return_code = process.wait()
    except OSError as exc:
        raise LibraryInstallError(f"Python 실행 실패: {exc}") from exc
    if return_code:
        if capture:
            for line in output:
                report(line.rstrip("\r\n"))
        raise LibraryInstallError(f"명령 실패 (종료 코드 {return_code}): {' '.join(arguments)}")
    return "".join(output)


def relax_versions(frozen_text):
    """일반 패키지의 ==만 >=로 바꾼다. URL·editable·주석은 보존한다."""
    pattern = re.compile(r"^([A-Za-z0-9][A-Za-z0-9_.-]*(?:\[[^\]\r\n]+\])?)==(?=\S)")
    return "".join(pattern.sub(r"\1>=", line, count=1)
                   for line in frozen_text.splitlines(keepends=True))


def install_missing_libraries(library_list, report=print):
    """현재 환경에 없는 필수 패키지를 설치한다."""
    for import_name, package_name in library_list:
        if importlib.util.find_spec(import_name) is None:
            report(f"[설치 중] {package_name}")
            _run(["-m", "pip", "install", package_name], report)
            importlib.invalidate_caches()


def install_and_update(library_list, report=print):
    """누락 설치 → freeze → 버전 제한 변경 → upgrade → 임시 파일 삭제."""
    if getattr(sys, "frozen", False):
        report("[안내] 패키징 실행 파일은 pip 설치·업데이트를 생략하고 포함된 라이브러리를 검증합니다.")
        return

    libraries = list(library_list)
    install_missing_libraries(libraries, report=report)
    # 전용 임시 폴더에 생성하여 프로젝트의 기존 requirements.txt를 보존한다.
    with tempfile.TemporaryDirectory(prefix="news_library_install_") as directory:
        requirements = Path(directory) / "requirements.txt"
        try:
            report("[설치 목록 생성] pip freeze → requirements.txt")
            frozen_text = _run(["-m", "pip", "freeze"], report, capture=True)
            requirements.write_text(frozen_text, encoding="utf-8")
            requirements.write_text(relax_versions(frozen_text), encoding="utf-8")
            report("[버전 조건 변경] == → >=")
            report("[업데이트 시작] 현재 Python 환경의 전체 패키지")
            _run(["-m", "pip", "install", "--upgrade", "-r", str(requirements)], report)
            importlib.invalidate_caches()
            # 이미 import한 모듈의 캐시에 의존하지 않고 새 Python에서 확인한다.
            report("[업데이트 검증] 필수 라이브러리 import")
            _run([
                "-c",
                "import importlib, sys; "
                "[importlib.import_module(name) for name in sys.argv[1:]]",
                *[name for name, _ in libraries],
            ], report)
            report("[업데이트 완료]")
        finally:
            requirements.unlink(missing_ok=True)
            report("[정리 완료] 임시 requirements.txt 삭제")


class LibraryManager:
    # (import 이름, pip 패키지 이름): 최초 설계 목록 + 현재 PySide6/DB 의존성
    library_list = [
        ("PySide6", "PySide6"),
        ("trafilatura", "trafilatura"),
        ("feedparser", "feedparser"),
        ("sklearn", "scikit-learn"),
        ("schedule", "schedule"),
        ("pandas", "pandas"),
        ("openpyxl", "openpyxl"),
        ("aiohttp", "aiohttp"),
        ("asyncpg", "asyncpg"),
        ("pgvector", "pgvector"),
        ("numpy", "numpy"),
        ("lxml", "lxml"),
        ("kiwipiepy", "kiwipiepy"),
    ]

    @classmethod
    def missing_libraries(cls):
        return [package for module, package in cls.library_list
                if importlib.util.find_spec(module) is None]

    @classmethod
    def update_library_config(cls, installed_list, report=print):
        """검증 결과를 공유 설정 객체와 config.py의 설치 목록에 저장한다."""
        config.INSTALLED_LIBRARIES = list(installed_list)
        temporary = None
        try:
            with open(CONFIG_PATH, "r", encoding="utf-8-sig", newline="") as stream:
                source = stream.read()
            tree = ast.parse(source, filename=str(CONFIG_PATH))
            assignments = []
            for node in tree.body:
                if isinstance(node, ast.Assign):
                    matches = any(isinstance(target, ast.Name)
                                  and target.id == "INSTALLED_LIBRARIES"
                                  for target in node.targets)
                    if matches:
                        if len(node.targets) != 1:
                            raise ValueError("INSTALLED_LIBRARIES는 단독 할당으로 작성해주세요.")
                        assignments.append(node)
                elif (isinstance(node, ast.AnnAssign)
                      and isinstance(node.target, ast.Name)
                      and node.target.id == "INSTALLED_LIBRARIES"):
                    assignments.append(node)

            newline = "\r\n" if "\r\n" in source else "\n"
            replacement = "INSTALLED_LIBRARIES = " + json.dumps(
                list(installed_list), ensure_ascii=False, indent=2,
            ).replace("\n", newline)
            # AST 위치는 UTF-8 바이트 기준이다. 다른 설정과 주석은 유지한다.
            lines = source.encode("utf-8").splitlines(keepends=True)
            payload = source.encode("utf-8")
            for node in reversed(assignments):
                begin = sum(len(line) for line in lines[:node.lineno - 1]) + node.col_offset
                finish = sum(len(line) for line in lines[:node.end_lineno - 1]) + node.end_col_offset
                payload = payload[:begin] + replacement.encode("utf-8") + payload[finish:]
            if not assignments:
                separator = "" if not source or source.endswith(("\n", "\r")) else newline
                payload += (separator + newline + replacement + newline).encode("utf-8")
            ast.parse(payload.decode("utf-8"), filename=str(CONFIG_PATH))
            with tempfile.NamedTemporaryFile(
                mode="wb", dir=CONFIG_PATH.parent,
                prefix=".config_libraries_", suffix=".tmp", delete=False,
            ) as stream:
                temporary = Path(stream.name)
                stream.write(payload)
            os.replace(temporary, CONFIG_PATH)
        except (OSError, SyntaxError, ValueError) as exc:
            # 저장 실패여도 실제 import 검증을 통과했으면 실행 가능하다.
            report(f"[안내] config.py에 설치 목록을 저장하지 못했습니다: {exc}")
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)

    @classmethod
    def ensure_library(cls, import_name, package_name, report=print):
        """없는 패키지만 현재 Python에 설치한 뒤 실제 import까지 검증한다."""
        try:
            if importlib.util.find_spec(import_name) is None:
                if getattr(sys, "frozen", False):
                    raise LibraryInstallError(
                        f"배포 파일에 {package_name}가 없습니다. 라이브러리를 포함해 다시 패키징해주세요."
                    )
                install_missing_libraries(
                    [(import_name, package_name)], report=report,
                )
            module = importlib.import_module(import_name)
        except LibraryInstallError:
            raise
        except Exception as exc:
            raise LibraryInstallError(
                f"{package_name} 설치 또는 import 검증 실패: {exc}"
            ) from exc
        report(f"[확인 완료] {import_name}")
        return module

    @classmethod
    def install_library(cls, report=print):
        installed = []
        modules = {}
        try:
            for import_name, package_name in cls.library_list:
                modules[import_name] = cls.ensure_library(import_name, package_name, report)
                installed.append(import_name)
        finally:
            # 중간 실패 시에도 이번 실행에서 실제 검증한 항목만 기록한다.
            cls.update_library_config(installed, report)
        return modules

    @classmethod
    def verification_libry(cls, report=print):
        """이전 기록과 현재 환경을 비교하고 전체 필수 라이브러리를 준비한다."""
        saved = getattr(config, "INSTALLED_LIBRARIES", [])
        missing = cls.missing_libraries()
        required = [name for name, _ in cls.library_list]
        if missing:
            report("[환경 변경 감지] 누락된 패키지: " + ", ".join(missing))
        elif not all(name in saved for name in required):
            report("[초기 확인] 설치 기록을 갱신합니다.")
        try:
            install_and_update(cls.library_list, report=report)
        except LibraryInstallError as exc:
            raise LibraryInstallError(f"라이브러리 자동 설치·업데이트 실패: {exc}") from exc
        # 업데이트 후 실제 import와 config.py 설치 기록을 갱신한다.
        return cls.install_library(report)

    @classmethod
    def verify_libraries(cls, report=print):
        return cls.verification_libry(report)