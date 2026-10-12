"""PostgreSQL 데이터 디렉터리 확인 및 클러스터 초기화."""
from __future__ import annotations

import logging
import os
from pathlib import Path
import shutil
import tempfile
import subprocess

from .common import _LOGGER, _logged

def _binary(name: str, bin_path: str | Path | None) -> str:
    if bin_path is not None:
        path = Path(bin_path) / (name + ('.exe' if os.name == 'nt' else ''))
        if path.is_file():
            return str(path.resolve())
    else:
        found = shutil.which(name)
        if found:
            return found
    raise FileNotFoundError(f'{name} 실행 파일을 찾을 수 없습니다. PostgreSQL bin_path를 전달하세요.')

@_logged
def _command(args: list[str], timeout: int = 90) -> subprocess.CompletedProcess:
    _LOGGER.info("외부 명령 실행: %s", Path(args[0]).name)
    result = subprocess.run(args, capture_output=True, text=True, errors='replace',
                            timeout=timeout, check=False)
    # 명령 인수는 계정/경로 등의 노출 방지를 위해 기록하지 않는다.
    _LOGGER.info("외부 명령 종료: %s / 종료 코드=%s", Path(args[0]).name, result.returncode)
    if result.stdout.strip():
        _LOGGER.info("명령 출력: %s", result.stdout.strip())
    if result.stderr.strip():
        _LOGGER.log(logging.ERROR if result.returncode else logging.INFO,
                    "명령 진단: %s", result.stderr.strip())
    return result

def _check(result: subprocess.CompletedProcess, action: str) -> None:
    if result.returncode:
        raise RuntimeError(f'{action} 실패: {result.stderr.strip() or result.stdout.strip()}')

@_logged
def step_1_prepare_server(storage_path: str | Path, user: str, password: str,
                     bin_path: str | Path | None) -> Path:
    """1. 물리 경로 확인. 없는 경우에만 initdb 실행."""
    base = Path(storage_path).expanduser().resolve()
    data = base if (base / 'PG_VERSION').is_file() or base.name == 'News_Data_Server' else base / 'News_Data_Server'
    if (data / 'PG_VERSION').is_file():
        if not (data / 'global' / 'pg_control').is_file():
            raise RuntimeError('기존 클러스터가 불완전합니다. 자동 재초기화하지 않습니다.')
        _LOGGER.info("1.2 기존 PostgreSQL 클러스터 사용: %s", data)
        return data
    _LOGGER.info('1.1 신규 PostgreSQL 클러스터 생성: %s', data)
    initdb = _binary('initdb', bin_path)
    if data.exists() and (not data.is_dir() or any(data.iterdir())):
        raise RuntimeError(f'비어 있지 않은 경로를 초기화할 수 없습니다: {data}')
    data.mkdir(parents=True, exist_ok=True)
    # 비밀번호는 명령 인수/환경변수에 넣지 않는다. 임시 파일은 즉시 제거한다.
    with tempfile.TemporaryDirectory(prefix='news_pg_init_') as temp:
        pwfile = Path(temp) / 'password'
        fd = os.open(pwfile, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, 'w', encoding='utf-8', newline='\n') as stream:
            stream.write(password + '\n')
        result = _command([initdb, '-D', str(data), '-U', user,
                           '--pwfile', str(pwfile), '--encoding=UTF8',
                           '--auth-local=scram-sha-256', '--auth-host=scram-sha-256'])
        _check(result, 'PostgreSQL 클러스터 생성')
    return data
