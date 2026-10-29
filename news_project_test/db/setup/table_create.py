"""
table.py의 정의로 누락 테이블·인덱스와 임베딩 파티션을 생성한다.

전체 테이블 준비와 마이그레이션 순서 관리는 table_setup.py가 담당한다.
"""
from __future__ import annotations

from typing import Iterable

from .common import _LOGGER, _logged
from .table import TABLE_DEFINITIONS

async def create_missing_tables(connection) -> None:
    """스키마·확장이 준비된 setup 트랜잭션 안에서 누락 테이블을 생성한다."""
    for name, create_sql, indexes in TABLE_DEFINITIONS:
        if await connection.fetchval("SELECT to_regclass($1)", name) is None:
            _LOGGER.info("3.1 누락 테이블 생성: %s", name)
            await connection.execute(create_sql)
            for index in indexes:
                _LOGGER.info("인덱스 생성: %s", index)
                await connection.execute(index)
        else:
            _LOGGER.info("3.2 기존 테이블 사용: %s", name)

@_logged
async def ensure_embedding_partitions(connection, years: Iterable[int]) -> None:
    """필요 연도를 명시해 호출. 과거/미래 기사 INSERT 전에 해당 연도를 준비한다."""
    years = tuple(years)
    if any(type(year) is not int or not 1 <= year <= 9998 for year in years):
        raise ValueError("파티션 연도는 1~9998 정수여야 합니다.")
    async with connection.transaction():
        await connection.execute("SELECT pg_advisory_xact_lock(736204185901)")
        for year in sorted(set(years)):
            name = f"public.news_embeddings_{year}"
            if await connection.fetchval("SELECT to_regclass($1)", name) is None:
                _LOGGER.info("연도 파티션 생성: %s", name)
                await connection.execute(f"""CREATE TABLE {name}
                    PARTITION OF public.news_embeddings
                    FOR VALUES FROM ({year}) TO ({year + 1})""")
            else:
                _LOGGER.info("기존 연도 파티션 확인: %s", name)
                attached = await connection.fetchval("""SELECT EXISTS (
                    SELECT 1 FROM pg_inherits WHERE inhrelid=to_regclass($1)
                    AND inhparent='public.news_embeddings'::regclass)""", name)
                if not attached:
                    raise RuntimeError(f"{name}은 임베딩 부모에 연결된 파티션이 아닙니다.")

async def check_vector_extension(connection) -> None:
    """DB에 확장을 만들기 전에 PostgreSQL 서버의 설치 가능 목록을 확인한다."""
    available = await connection.fetchval(
        "SELECT EXISTS (SELECT 1 FROM pg_available_extensions WHERE name='vector')"
    )
    if not available:
        version = await connection.fetchval("SHOW server_version")
        raise RuntimeError(
            f"접속한 PostgreSQL {version} 서버에서 pgvector 확장 설치 파일을 찾지 못했습니다.\n"
            "Python의 pip install pgvector와 별도로 PostgreSQL 서버용 확장을 설치해야 합니다.\n"
            "서버와 같은 PostgreSQL 버전/아키텍처용 pgvector를 설치한 뒤 다시 실행하세요.\n"
            "Windows 설치 안내: https://github.com/pgvector/pgvector#windows"
        )