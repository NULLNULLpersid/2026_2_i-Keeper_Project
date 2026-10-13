"""라이브러리 준비 및 프로젝트 공통 모듈 등록. 작업은 명시적으로 호출한다."""
import builtins
import importlib
import json
import os
import platform
import subprocess
import sys
import threading
import time
from pathlib import Path

from init import config
from .library_install import LibraryInstallError, LibraryManager


class InitializationError(RuntimeError):
    """라이브러리 준비 또는 프로젝트 모듈 로딩 실패."""

def register_shared_modules(modules, report=print):
    """표준/외부/설정 모듈을 먼저 등록하고 커스텀 모듈을 순서대로 등록한다."""
    shared = {
        "subprocess": subprocess, "sys": sys, "importlib": importlib,
        "json": json, "time": time, "os": os, "platform": platform,
        "threading": threading, "config": config, "init": sys.modules[__name__],
    }
    shared.update(modules)
    for name in ("QtCore", "QtGui", "QtWidgets"):
        shared[name] = importlib.import_module(f"PySide6.{name}")
    for name, module in shared.items():
        setattr(builtins, name, module)

    # crawler.py와 crawler/가 공존하므로 현재 사용 중인 실행 모듈을 명시한다.
    custom_modules = [
        ("gui_common", "gui_common"),
        ("crawler", "collection.crawler.scraping_run"),
        ("select_media", "collection.media_select.media_select_gui"),
        ("db_setting", "setting.setting_gui"),
        ("gui_init", "init.init_gui"),
        ("gui_main", "main_gui"),
    ]
    for alias, module_name in custom_modules:
        try:
            module = importlib.import_module(module_name)
        except Exception as exc:
            raise InitializationError(f"프로젝트 모듈 로딩 실패 ({module_name}): {exc}") from exc
        setattr(builtins, alias, module)
        shared[alias] = module
        report(f"[모듈 준비 완료] {module_name}")
    return shared


def check_environment(report=None):
    """라이브러리 준비 → 전역 등록 → 프로젝트 모듈 로딩 → 경로 안내."""
    messages = []

    def emit(message):
        messages.append(message)
        if report is not None:
            report(message)

    try:
        modules = LibraryManager.verify_libraries(emit)
    except LibraryInstallError as exc:
        raise InitializationError(f"라이브러리 준비 실패: {exc}") from exc
    register_shared_modules(modules, emit)
    raw_path = str(getattr(config, "POSTGRES_BIN", "")).strip()
    executable = "pg_ctl.exe" if platform.system() == "Windows" else "pg_ctl"
    if not raw_path or not (Path(raw_path) / executable).is_file():
        emit("[안내] PostgreSQL bin 경로를 환경 설정에서 지정해주세요.")
    else:
        emit("[확인 완료] PostgreSQL 실행 파일 경로")
    emit("초기화 완료. PostgreSQL 연결과 pgvector 확장은 수집 시작 시 확인합니다.")
    return messages