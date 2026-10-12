"""DB 설정 모듈을 총괄해 서버 준비, 접속, 테이블 생성을 실행."""
from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

# setting.py와 setting/을 함께 사용하기 위한 하위 모듈 검색 경로.
__path__ = [str(Path(__file__).with_suffix(''))]

from .setting.common import _LOGGER, _logged
from .setting.server_init import step_1_prepare_server
from .setting.server_create import step_2_connect_server, _verify_directory
from .setting.table_create import (
    TABLE_DEFINITIONS, ensure_embedding_partitions, step_3_prepare_tables, validate_schema,
)

def _connection_values(*, storage_path, user, password, host, port, database,
                       bin_path, embedding_years, timeout):
    if host not in ('localhost', '127.0.0.1', '::1'):
        raise ValueError('물리 경로를 관리하는 이 함수는 로컬 PostgreSQL 서버 전용입니다.')
    if not user or not password or any(ch in password for ch in '\r\n\x00'):
        raise ValueError('사용자/암호가 필요하며 암호에 줄바꿈 또는 NUL을 넣을 수 없습니다.')
    if type(port) is not int or not 1 <= port <= 65535 or type(timeout) is not int or timeout < 1:
        raise ValueError('port 또는 timeout 값이 올바르지 않습니다.')
    if not database or '\x00' in database or len(database.encode('utf-8')) > 63:
        raise ValueError('데이터베이스 이름은 1~63 UTF-8 바이트여야 합니다.')
    years = tuple(embedding_years) if embedding_years is not None else tuple(
        range(2025, datetime.now(timezone.utc).year + 2))
    if any(type(year) is not int or not 1 <= year <= 9998 for year in years):
        raise ValueError('embedding_years에는 1~9998 정수만 지정하세요.')
    base = Path(storage_path).expanduser().resolve()
    data = base if (base / 'PG_VERSION').is_file() or base.name == 'News_Data_Server' else base / 'News_Data_Server'
    return data, years

async def _prepare_connection(connection, years):
    """연결된 DB의 누락 테이블과 pgvector codec을 확인한다."""
    from pgvector.asyncpg import register_vector
    try:
        await step_3_prepare_tables(connection, years)
        await validate_schema(connection)
        await register_vector(connection, schema='public')
        return connection
    except BaseException:
        await connection.close()
        raise

@_logged
async def initial_connect_news_database(*, storage_path: str | Path, user: str,
                                        password: str, host: str = '127.0.0.1',
                                        port: int = 5432, database: str = 'News_Data_Server',
                                        bin_path: str | Path | None = None,
                                        embedding_years: Iterable[int] | None = None,
                                        timeout: int = 30):
    """최초/복구 연결 경로: 서버 디렉터리와 실행 상태를 준비하고 DB·테이블을 보장한다."""
    data, years = _connection_values(
        storage_path=storage_path, user=user, password=password, host=host, port=port,
        database=database, bin_path=bin_path, embedding_years=embedding_years, timeout=timeout,
    )
    data = await asyncio.to_thread(step_1_prepare_server, storage_path, user, password, bin_path)
    connection = await step_2_connect_server(
        data=data, user=user, password=password, host=host, port=port,
        database=database, bin_path=bin_path, timeout=timeout,
    )
    return await _prepare_connection(connection, years)

@_logged
async def reconnect_news_database(*, storage_path: str | Path, user: str,
                                  password: str, host: str = '127.0.0.1',
                                  port: int = 5432, database: str = 'News_Data_Server',
                                  bin_path: str | Path | None = None,
                                  embedding_years: Iterable[int] | None = None,
                                  timeout: int = 30):
    """재연결 경로: 실행 중인 지정 클러스터에 바로 연결하며 서버를 기동하지 않는다."""
    import asyncpg
    data, years = _connection_values(
        storage_path=storage_path, user=user, password=password, host=host, port=port,
        database=database, bin_path=bin_path, embedding_years=embedding_years, timeout=timeout,
    )
    connection = await asyncpg.connect(
        host=host, port=port, user=user, password=password, database=database, timeout=timeout,
    )
    try:
        await _verify_directory(connection, data)
    except BaseException:
        await connection.close()
        raise
    return await _prepare_connection(connection, years)

async def connect_news_database(**options):
    """기존 호출과의 호환용 별칭. 서버 준비가 포함된 초기 연결을 수행한다."""
    return await initial_connect_news_database(**options)

def validate_url(url: str) -> str:
    """HTTP(S) URL의 형식만 검사하고 원본 문자열을 그대로 반환한다."""
    from urllib.parse import urlsplit
    if not isinstance(url, str) or not url or any(c.isspace() for c in url):
        raise ValueError('공백 없는 HTTP(S) 기사 URL이 필요합니다.')
    parsed = urlsplit(url)
    if parsed.scheme.lower() not in ('http', 'https') or not parsed.hostname or parsed.username or parsed.password:
        raise ValueError('인증 정보 없는 HTTP(S) 기사 URL이 필요합니다.')
    _ = parsed.port  # 잘못된 포트만 검사하며 URL을 재작성하지 않는다.
    return url

@asynccontextmanager
async def configured_database(settings=None, **overrides):
    """재연결을 우선 시도하고, 연결/DB가 없을 때만 초기 연결 경로를 쓴다.
    연결 종료 시 항상 close.

    async with configured_database(config) as connection:
        await db_manager.save_news(connection, ...)
    동일 연결에서 DB 함수를 동시에 실행하지 말 것(HTTP 요청만 병렬 처리 가능).
    """
    if settings is None:
        from init import config as settings
    options = dict(storage_path=settings.SAVE_PATH, user=settings.DB_USER,
                   password=settings.DB_PASSWORD, host=settings.DB_HOST,
                   port=settings.DB_PORT, database=settings.DB_NAME,
                   bin_path=settings.POSTGRES_BIN or None)
    options.update(overrides)
    import asyncpg
    try:
        connection = await reconnect_news_database(**options)
    except (asyncpg.PostgresConnectionError, asyncpg.InvalidCatalogNameError,
            OSError, asyncio.TimeoutError) as error:
        _LOGGER.info('기존 DB 재연결 실패. 초기 연결 경로로 전환: %s', type(error).__name__)
        connection = await initial_connect_news_database(**options)
    try:
        yield connection
    finally:
        await connection.close()

# DB 저장·조회 모듈에서 공유하는 실행 이력 데코레이터
log_database_call = _logged

__all__ = [
    "LOG_PATH", "TABLE_DEFINITIONS", "step_1_prepare_server", "step_2_connect_server",
    "step_3_prepare_tables", "ensure_embedding_partitions", "initial_connect_news_database",
    "reconnect_news_database", "connect_news_database", "log_database_call",
    "validate_schema", "validate_url", "configured_database",
]
from .setting.common import LOG_PATH
