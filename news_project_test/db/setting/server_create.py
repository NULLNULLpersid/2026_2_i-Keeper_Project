"""실행 중인 PostgreSQL 서버 확인, 필요 시 기동 및 DB 접속."""
from __future__ import annotations

import asyncio
import os
from pathlib import Path

from .common import _LOGGER, _logged
from .server_init import _binary, _command, _check

@_logged
async def _verify_directory(connection, data: Path) -> None:
    actual = Path(await connection.fetchval('SHOW data_directory')).resolve()
    if not os.path.samefile(actual, data):
        raise RuntimeError('접속한 서버와 입력받은 데이터 디렉터리가 다릅니다.')

@_logged
async def step_2_connect_server(*, data: Path, user: str, password: str,
                                host: str, port: int, database: str,
                                bin_path: str | Path | None, timeout: int):
    """2. 접속 가능하면 기존 서버 사용, 중지 상태일 때만 가동 후 접속."""
    import asyncpg

    params = dict(host=host, port=port, user=user, password=password, timeout=timeout)

    # 2. 실제 접속 검사. 실패하면 pg_ctl로 해당 클러스터의 실행 여부를 확인.
    try:
        admin = await asyncpg.connect(database='postgres', **params)
    except (OSError, asyncio.TimeoutError, asyncpg.PostgresError) as connection_error:
        _LOGGER.warning('최초 접속 실패. 서버 상태 확인', exc_info=True)
        ctl = _binary('pg_ctl', bin_path)
        state = await asyncio.to_thread(_command, [ctl, 'status', '-D', str(data)])
        if state.returncode == 0:
            raise RuntimeError('서버는 실행 중입니다. 포트/계정/암호/인증 설정을 확인하세요.') from connection_error
        if state.returncode != 3:
            _check(state, 'PostgreSQL 상태 확인')
        # 인증/DB 오류는 다른 서버가 해당 주소에서 응답했다는 뜻이므로 시작하지 않는다.
        if isinstance(connection_error, asyncpg.PostgresError):
            raise RuntimeError('해당 접속 주소의 서버가 오류를 반환했습니다. 자동 기동을 중단합니다.') from connection_error
        _LOGGER.info('2.2 중지된 서버 가동 후 접속')
        started = await asyncio.to_thread(_command, [ctl, 'start', '-D', str(data),
            '-l', str(data / 'server.log'), '-w', '-t', str(timeout),
            '-o', f'-p {port} -h localhost'], timeout + 15)
        _check(started, 'PostgreSQL 시작')
        admin = await asyncpg.connect(database='postgres', **params)
    _LOGGER.info('2. 서버 접속 성공')
    try:
        await _verify_directory(admin, data)
        await admin.execute('SELECT pg_advisory_lock(736204185902)')
        try:
            exists = await admin.fetchval('SELECT 1 FROM pg_database WHERE datname=$1', database)
            if not exists:
                quoted = '"' + database.replace('"', '""') + '"'
                _LOGGER.info('데이터베이스 생성: %s', database)
                await admin.execute(f'CREATE DATABASE {quoted}')
            else:
                _LOGGER.info('기존 데이터베이스 사용: %s', database)
        finally:
            await admin.execute('SELECT pg_advisory_unlock(736204185902)')
    finally:
        await admin.close()
    connection = await asyncpg.connect(database=database, **params)
    try:
        await _verify_directory(connection, data)
        return connection
    except BaseException:
        await connection.close()
        raise
