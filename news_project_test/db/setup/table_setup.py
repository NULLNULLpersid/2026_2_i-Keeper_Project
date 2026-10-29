"""table.py의 구조를 기준으로 테이블 준비·마이그레이션·검증을 관리한다."""
from __future__ import annotations

from typing import Iterable

from .common import _LOGGER, _logged
from .table import TABLE_DEFINITIONS
from .table_create import (
    check_vector_extension, create_missing_tables, ensure_embedding_partitions,
)

@_logged
async def step_3_prepare_tables(connection, years: Iterable[int]) -> None:
    """3. 누락 테이블 생성 및 원본 URL 스키마로 전환."""
    await check_vector_extension(connection)
    async with connection.transaction():
        from ..news_archive import NEWS_WRITE_LOCK
        await connection.execute("SELECT pg_advisory_xact_lock($1)", NEWS_WRITE_LOCK)
        await connection.execute("SELECT pg_advisory_xact_lock(736204185901)")
        await connection.execute("CREATE SCHEMA IF NOT EXISTS analysis")
        _LOGGER.info("pgvector 확장 확인 및 필요 시 생성")
        await connection.execute("CREATE EXTENSION IF NOT EXISTS vector WITH SCHEMA public")
        if await connection.fetchval("SELECT to_regtype('public.halfvec')") is None:
            raise RuntimeError("public 스키마에 pgvector >= 0.7의 halfvec 타입이 필요합니다.")
        await create_missing_tables(connection)
        await migrate_news_labels(connection)
        await migrate_author_email(connection)
        await migrate_original_urls(connection)
        await ensure_embedding_partitions(connection, years)

async def migrate_news_labels(connection) -> None:
    """기존 단일 분류를 첫 라벨로 보존하고 두 번째 라벨 컬럼을 준비한다.

    기존 기사는 label2_id=NULL로 유지한다. 확인되지 않은 두 번째 정답을
    첫 라벨로 임의 복제하지 않는다. 반복 실행해도 같은 결과를 유지한다.
    """
    from ..news_archive import NEWS_WRITE_LOCK
    async with connection.transaction():
        await connection.execute("SELECT pg_advisory_xact_lock($1)", NEWS_WRITE_LOCK)
        for table in ("today_news", "news", "old_news"):
            columns = {row["column_name"] for row in await connection.fetch(
                "SELECT column_name FROM information_schema.columns "
                "WHERE table_schema='public' AND table_name=$1", table,
            )}
            if "category_id" in columns and "label1_id" not in columns:
                # RENAME은 기존 값과 외래키 연결을 함께 유지한다.
                await connection.execute(
                    f"ALTER TABLE public.{table} RENAME COLUMN category_id TO label1_id"
                )
            elif "category_id" in columns and "label1_id" in columns:
                # 중간 버전의 두 컬럼이 공존하면 서로 다른 값을 조용히 덮어쓰지 않는다.
                conflicting = await connection.fetchval(
                    f"SELECT EXISTS (SELECT 1 FROM public.{table} "
                    "WHERE category_id IS NOT NULL AND label1_id IS NOT NULL "
                    "AND category_id <> label1_id)"
                )
                if conflicting:
                    raise RuntimeError(f"{table}: category_id와 label1_id가 충돌합니다.")
                await connection.execute(
                    f"UPDATE public.{table} SET label1_id=category_id "
                    "WHERE label1_id IS NULL AND category_id IS NOT NULL"
                )
            await connection.execute(
                f"ALTER TABLE public.{table} ADD COLUMN IF NOT EXISTS "
                "label1_id BIGINT REFERENCES public.categories(id)"
            )
            await connection.execute(
                f"ALTER TABLE public.{table} ADD COLUMN IF NOT EXISTS "
                "label2_id BIGINT REFERENCES public.categories(id)"
            )

async def migrate_author_email(connection) -> None:
    """기존 기사를 유지하며 세 본문 테이블에 선택적 작성자 이메일 컬럼을 추가한다."""
    from ..news_archive import NEWS_WRITE_LOCK
    async with connection.transaction():
        await connection.execute("SELECT pg_advisory_xact_lock($1)", NEWS_WRITE_LOCK)
        for table in ("today_news", "news", "old_news"):
            await connection.execute(
                f"ALTER TABLE public.{table} ADD COLUMN IF NOT EXISTS author_email TEXT"
            )
            await connection.execute(
                f"ALTER TABLE public.{table} ADD COLUMN IF NOT EXISTS author_contacts JSONB NOT NULL DEFAULT '[]'::jsonb"
            )

async def validate_schema(connection) -> None:
    """구형 동명 테이블을 감지한다. 기존 데이터를 자동 변경/삭제하지 않는다."""
    import re
    for table, ddl, _ in TABLE_DEFINITIONS:
        expected = set(re.findall(
            r"^\s*([a-z_][a-z_0-9]*)\s+(?:BIGINT|SMALLINT|INTEGER|TEXT|VARCHAR|BYTEA|TIMESTAMPTZ|DOUBLE|JSONB|public\.halfvec)\b",
            ddl, flags=re.MULTILINE,
        ))
        actual = {row["attname"] for row in await connection.fetch(
            "SELECT attname FROM pg_attribute WHERE attrelid=to_regclass($1) "
            "AND attnum > 0 AND NOT attisdropped", table
        )}
        missing = expected - actual
        if missing:
            raise RuntimeError(f"{table}: 필수 열 {sorted(missing)} 누락. 기존 DB 스키마 마이그레이션이 필요합니다.")

async def migrate_original_urls(connection) -> None:
    """기존 뉴스의 URL은 유지하고 폐기된 컬럼을 트랜잭션 안에서 제거한다."""
    from ..news_archive import NEWS_WRITE_LOCK
    async with connection.transaction():
        await connection.execute("SELECT pg_advisory_xact_lock($1)", NEWS_WRITE_LOCK)
        legacy = await connection.fetchval("""SELECT EXISTS (
            SELECT 1 FROM information_schema.columns
            WHERE table_schema='public'
              AND table_name IN ('today_news','news','old_news')
              AND column_name IN ('canonical_url','canonical_url_hash'))""")
        index_exists = await connection.fetchval("SELECT to_regclass('public.uq_today_news_url')")
        if not legacy and index_exists is not None:
            return
        await connection.execute("LOCK TABLE public.today_news, public.news, public.old_news IN ACCESS EXCLUSIVE MODE")
        if await connection.fetchval("""SELECT EXISTS (
            SELECT 1 FROM public.today_news GROUP BY url HAVING count(*) > 1)"""):
            raise RuntimeError("today_news에 동일한 원본 URL이 여러 건 있습니다. 중복 기사를 확인한 뒤 다시 연결하세요. DB 변경은 취소됩니다.")
        await connection.execute("CREATE UNIQUE INDEX IF NOT EXISTS uq_today_news_url ON public.today_news(url)")
        for table in ("today_news", "news", "old_news"):
            await connection.execute(f"ALTER TABLE public.{table} DROP COLUMN IF EXISTS canonical_url, DROP COLUMN IF EXISTS canonical_url_hash")
        _LOGGER.info("원본 URL 비교 스키마 전환 완료")