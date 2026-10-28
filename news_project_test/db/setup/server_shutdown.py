"""
프로그램 정상 종료 시 등록된 로컬 PostgreSQL 서버를 종료한다.

배치 위치: db/setting/server_shutdown.py
DB 연결을 닫거나 뉴스 수집을 중단하는 것만으로는 서버를 종료하지 않는다.
Python 정상 종료, sys.exit(), 처리되지 않은 예외에 따른 종료 시 atexit이 실행된다.
작업 관리자 강제 종료, os._exit(), 전원 차단에서는 실행을 보장할 수 없다.
등록한 서버는 기존 실행 중인 서버를 재사용한 경우에도 프로그램 종료 시 중지한다.
"""
from __future__ import annotations

import atexit
import os
from pathlib import Path
import threading

from .common import _LOGGER
from .server_init import _binary, _command, _check

_SERVERS: dict[Path, tuple[str, int]] = {}
_REGISTRY_LOCK = threading.RLock()
_HOOK_REGISTERED = False
_OWNER_PID = os.getpid()

def _validate_timeout(timeout: int) -> None:
    if type(timeout) is not int or timeout < 1:
        raise ValueError('서버 종료 timeout은 양의 정수여야 합니다.')

def _stop_server(data: Path, ctl: str, timeout: int) -> bool:
    state = _command([ctl, 'status', '-D', str(data)], timeout=timeout)
    if state.returncode == 3:
        _LOGGER.info('이미 중지된 PostgreSQL 서버: %s', data)
        return False
    _check(state, 'PostgreSQL 종료 전 상태 확인')
    # fast는 미완료 트랜잭션을 롤백하고 연결을 닫은 뒤 정상 종료한다.
    # immediate 또는 OS 프로세스 강제 종료는 사용하지 않는다.
    result = _command(
        [ctl, 'stop', '-D', str(data), '-m', 'fast', '-w', '-t', str(timeout)],
        timeout=timeout + 15,
    )
    _check(result, 'PostgreSQL 서버 종료')
    _LOGGER.info('PostgreSQL 서버 종료 완료: %s', data)
    return True

def stop_postgresql_server(*, data: str | Path,
                           bin_path: str | Path | None = None,
                           timeout: int = 30) -> bool:
    """
    지정한 데이터 디렉터리의 서버를 종료한다. 이미 중지됐다면 False.

    data에는 SAVE_PATH가 아닌 실제 클러스터 경로를 전달한다.
    수동 호출은 즉시 서버를 종료하므로 프로그램 종료 단계에서 사용한다.
    실패 시 예외를 전달하며 데이터 디렉터리나 저장 기사를 삭제하지 않는다.
    """
    _validate_timeout(timeout)
    path = Path(data).expanduser().resolve()
    return _stop_server(path, _binary('pg_ctl', bin_path), timeout)

def shutdown_registered_servers() -> None:
    # fork된 자식 프로세스가 부모 프로그램의 서버를 종료하지 않도록 한다.
    if os.getpid() != _OWNER_PID:
        return
    with _REGISTRY_LOCK:
        servers = list(_SERVERS.items())
        _SERVERS.clear()
    for data, (ctl, timeout) in reversed(servers):
        try:
            _stop_server(data, ctl, timeout)
        except Exception:
            # 한 서버의 실패가 나머지 서버의 종료를 막지 않도록 기록하고 계속한다.
            _LOGGER.exception('프로그램 종료 시 PostgreSQL 서버 중지 실패: %s', data)

def register_server_shutdown(*, data: str | Path,
                             bin_path: str | Path | None = None,
                             timeout: int = 30) -> None:
    """
    확인된 프로그램용 로컬 서버를 정상 종료 훅에 등록한다.

    같은 클러스터를 반복 연결해도 등록은 하나이며, 수집 종료에는 실행되지 않는다.
    pg_ctl 경로를 미리 확인하므로 종료 시 실행 파일을 찾지 못하는 오류를 줄인다.
    """
    global _HOOK_REGISTERED
    _validate_timeout(timeout)
    path = Path(data).expanduser().resolve()
    ctl = str(Path(_binary('pg_ctl', bin_path)).resolve())
    with _REGISTRY_LOCK:
        if not _HOOK_REGISTERED:
            atexit.register(shutdown_registered_servers)
            _HOOK_REGISTERED = True
        _SERVERS[path] = (ctl, timeout)
    _LOGGER.info('프로그램 정상 종료 시 서버 중지 등록: %s', path)