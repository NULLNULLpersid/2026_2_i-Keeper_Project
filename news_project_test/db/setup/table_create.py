"""뉴스 서비스의 PostgreSQL 테이블·인덱스·연도 파티션 생성."""
from __future__ import annotations

import re
from typing import Iterable

from .common import _LOGGER, _logged

CREATE_NEWS_ID = """
CREATE TABLE public.news_id (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY
);
"""

CREATE_PUBLISHERS = """
CREATE TABLE public.publishers (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,

    name VARCHAR(100) NOT NULL UNIQUE
);
"""

CREATE_CATEGORIES = """
CREATE TABLE public.categories (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,

    name VARCHAR(20) NOT NULL,

    parent_id BIGINT
        REFERENCES public.categories(id),

    UNIQUE(parent_id, name),

    CHECK(parent_id IS NULL OR parent_id <> id)
);
"""

CREATE_KEYWORDS = """
CREATE TABLE public.keywords (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,

    keyword VARCHAR(50) NOT NULL UNIQUE
);
"""

CREATE_EMBEDDING_MODELS = """
CREATE TABLE public.embedding_models (
    id SMALLINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,

    model_name VARCHAR(100) NOT NULL UNIQUE,

    dimension INTEGER NOT NULL CHECK(dimension > 0)
);
"""

CREATE_TODAY_NEWS = """
CREATE TABLE public.today_news (
    news_id BIGINT PRIMARY KEY
        REFERENCES public.news_id(id),

    publisher_id BIGINT NOT NULL
        REFERENCES public.publishers(id),

    category_id BIGINT
        REFERENCES public.categories(id),

    title TEXT NOT NULL,

    url TEXT NOT NULL,

    published_at TIMESTAMPTZ NOT NULL,

    author VARCHAR(100),

    author_email TEXT,
    author_contacts JSONB NOT NULL DEFAULT '[]'::jsonb,

    content TEXT NOT NULL
);
"""

CREATE_NEWS = """
CREATE TABLE public.news (
    news_id BIGINT PRIMARY KEY
        REFERENCES public.news_id(id),

    publisher_id BIGINT
        REFERENCES public.publishers(id),

    category_id BIGINT
        REFERENCES public.categories(id),

    title TEXT,

    url TEXT,

    published_at TIMESTAMPTZ,

    author VARCHAR(100),

    author_email TEXT,
    author_contacts JSONB NOT NULL DEFAULT '[]'::jsonb,

    content TEXT
);
"""

CREATE_OLD_NEWS = """
CREATE TABLE public.old_news (
    news_id BIGINT PRIMARY KEY
        REFERENCES public.news_id(id),

    publisher_id BIGINT
        REFERENCES public.publishers(id),

    category_id BIGINT
        REFERENCES public.categories(id),

    title TEXT,

    url TEXT,

    published_at TIMESTAMPTZ,

    author VARCHAR(100),

    author_email TEXT,
    author_contacts JSONB NOT NULL DEFAULT '[]'::jsonb,

    content TEXT
);
"""

CREATE_NEWS_LOCATION = """
CREATE TABLE public.news_location (
    news_id BIGINT PRIMARY KEY
        REFERENCES public.news_id(id),

    storage_type VARCHAR CHECK(storage_type IN ('today', 'news', 'old'))
);
"""

CREATE_NEWS_KEYWORDS = """
CREATE TABLE public.news_keywords (
    news_id BIGINT NOT NULL
        REFERENCES public.news_id(id),

    keyword_id BIGINT NOT NULL
        REFERENCES public.keywords(id),

    keyword_score DOUBLE PRECISION NOT NULL CHECK(keyword_score >= 0),

    keyword_rank INTEGER NOT NULL CHECK(keyword_rank > 0),

    PRIMARY KEY(news_id, keyword_id),

    UNIQUE(news_id, keyword_rank)
);
"""

CREATE_NEWS_EMBEDDINGS = """
CREATE TABLE public.news_embeddings (
    news_id BIGINT
        REFERENCES public.news_id(id),

    model_id SMALLINT
        REFERENCES public.embedding_models(id),

    embedding_year SMALLINT,

    embedding public.halfvec,

    PRIMARY KEY(news_id, model_id, embedding_year)
) PARTITION BY RANGE (embedding_year);
"""

CREATE_NEWS_EMBEDDING_LOCATOR = """
CREATE TABLE public.news_embedding_locator (
    news_id BIGINT
        REFERENCES public.news_id(id),

    model_id SMALLINT
        REFERENCES public.embedding_models(id),

    embedding_year SMALLINT,

    PRIMARY KEY(news_id, model_id)
);
"""

CREATE_LEARNING_DATA_NEWS = """
CREATE TABLE public.learning_data_news (
    news_id BIGINT PRIMARY KEY
        REFERENCES public.news_id(id),

    dataset_name VARCHAR,

    dataset_version VARCHAR,

    data_split VARCHAR CHECK(data_split IN ('train', 'valid', 'test'))
);
"""

CREATE_ANALYSIS_RUNS = """
CREATE TABLE analysis.analysis_runs (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,

    period_start TIMESTAMPTZ,

    period_end TIMESTAMPTZ,

    bucket_unit VARCHAR CHECK(bucket_unit IN ('hour', 'day', 'week', 'month')),

    embedding_model_id SMALLINT
        REFERENCES public.embedding_models(id),

    filters JSONB,

    algorithm_name VARCHAR,

    algorithm_version VARCHAR,

    request_hash BYTEA UNIQUE,

    status VARCHAR CHECK(status IN ('running', 'completed', 'failed')),

    created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,

    completed_at TIMESTAMPTZ
);
"""

CREATE_ANALYSIS_OVERVIEW = """
CREATE TABLE analysis.analysis_overview (
    analysis_id BIGINT
        REFERENCES analysis.analysis_runs(id) PRIMARY KEY,

    news_count BIGINT,

    publisher_count BIGINT,

    category_count BIGINT,

    author_count BIGINT,

    keyword_count BIGINT,

    issue_count BIGINT
);
"""

CREATE_ANALYSIS_KEYWORD_STATS = """
CREATE TABLE analysis.analysis_keyword_stats (
    analysis_id BIGINT
        REFERENCES analysis.analysis_runs(id),

    keyword_id BIGINT
        REFERENCES public.keywords(id),

    news_count BIGINT,

    score_sum DOUBLE PRECISION,

    score_max DOUBLE PRECISION,

    rank_sum BIGINT,

    analysis_score DOUBLE PRECISION,

    result_rank INTEGER,

    PRIMARY KEY(analysis_id, keyword_id),

    UNIQUE(analysis_id, result_rank)
);
"""

CREATE_ANALYSIS_CATEGORY_STATS = """
CREATE TABLE analysis.analysis_category_stats (
    analysis_id BIGINT
        REFERENCES analysis.analysis_runs(id),

    category_id BIGINT
        REFERENCES public.categories(id),

    news_count BIGINT,

    PRIMARY KEY(analysis_id, category_id)
);
"""

CREATE_ANALYSIS_PUBLISHER_STATS = """
CREATE TABLE analysis.analysis_publisher_stats (
    analysis_id BIGINT
        REFERENCES analysis.analysis_runs(id),

    publisher_id BIGINT
        REFERENCES public.publishers(id),

    news_count BIGINT,

    PRIMARY KEY(analysis_id, publisher_id)
);
"""

CREATE_ANALYSIS_AUTHOR_STATS = """
CREATE TABLE analysis.analysis_author_stats (
    analysis_id BIGINT
        REFERENCES analysis.analysis_runs(id),

    author_name VARCHAR(100),

    news_count BIGINT,

    PRIMARY KEY(analysis_id, author_name)
);
"""

CREATE_ANALYSIS_TIME_BUCKETS = """
CREATE TABLE analysis.analysis_time_buckets (
    analysis_id BIGINT
        REFERENCES analysis.analysis_runs(id),

    bucket_start TIMESTAMPTZ,

    bucket_end TIMESTAMPTZ,

    news_count BIGINT,

    PRIMARY KEY(analysis_id, bucket_start)
);
"""

CREATE_ANALYSIS_ISSUES = """
CREATE TABLE analysis.analysis_issues (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,

    analysis_id BIGINT
        REFERENCES analysis.analysis_runs(id),

    cluster_no INTEGER,

    issue_name TEXT,

    representative_news_id BIGINT
        REFERENCES public.news_id(id),

    news_count BIGINT,

    average_similarity DOUBLE PRECISION,

    first_published_at TIMESTAMPTZ,

    last_published_at TIMESTAMPTZ,

    trend_label VARCHAR,

    trend_score DOUBLE PRECISION,

    UNIQUE(analysis_id, cluster_no)
);
"""

CREATE_ANALYSIS_ISSUE_MEMBERS = """
CREATE TABLE analysis.analysis_issue_members (
    issue_id BIGINT
        REFERENCES analysis.analysis_issues(id),

    news_id BIGINT
        REFERENCES public.news_id(id),

    similarity_score DOUBLE PRECISION,

    member_rank INTEGER,

    PRIMARY KEY(issue_id, news_id)
);
"""

CREATE_ANALYSIS_ISSUE_KEYWORDS = """
CREATE TABLE analysis.analysis_issue_keywords (
    issue_id BIGINT
        REFERENCES analysis.analysis_issues(id),

    keyword_id BIGINT
        REFERENCES public.keywords(id),

    keyword_score DOUBLE PRECISION,

    keyword_rank INTEGER,

    PRIMARY KEY(issue_id, keyword_id),

    UNIQUE(issue_id, keyword_rank)
);
"""

CREATE_ANALYSIS_ISSUE_TIMESERIES = """
CREATE TABLE analysis.analysis_issue_timeseries (
    issue_id BIGINT
        REFERENCES analysis.analysis_issues(id),

    bucket_start TIMESTAMPTZ,

    news_count BIGINT,

    popularity_score DOUBLE PRECISION,

    PRIMARY KEY(issue_id, bucket_start)
);
"""

CREATE_ANALYSIS_SIMILAR_NEWS = """
CREATE TABLE analysis.analysis_similar_news (
    analysis_id BIGINT NOT NULL
        REFERENCES analysis.analysis_runs(id)
        ON DELETE CASCADE,

    source_news_id BIGINT NOT NULL
        REFERENCES public.news_id(id),

    similar_news_id BIGINT NOT NULL
        REFERENCES public.news_id(id),

    similarity_score DOUBLE PRECISION NOT NULL,

    similarity_rank INTEGER NOT NULL,

    PRIMARY KEY (
        analysis_id,
        source_news_id,
        similar_news_id
    ),

    CONSTRAINT uq_analysis_similar_rank
        UNIQUE (
            analysis_id,
            source_news_id,
            similarity_rank
        ),

    CONSTRAINT chk_similar_news_not_self
        CHECK (source_news_id <> similar_news_id)
);
"""

TABLE_DEFINITIONS = (
    ('public.news_id', CREATE_NEWS_ID, ()),
    ('public.publishers', CREATE_PUBLISHERS, ()),
    ('public.categories', CREATE_CATEGORIES, ('CREATE UNIQUE INDEX uq_categories_root_name ON public.categories(name) WHERE parent_id IS NULL',)),
    ('public.keywords', CREATE_KEYWORDS, ()),
    ('public.embedding_models', CREATE_EMBEDDING_MODELS, ()),
    ('public.today_news', CREATE_TODAY_NEWS, ('CREATE INDEX ix_today_news_published_at ON public.today_news(published_at)', 'CREATE UNIQUE INDEX uq_today_news_url ON public.today_news(url)')),
    ('public.news', CREATE_NEWS, ('CREATE INDEX ix_news_published_at ON public.news(published_at)',)),
    ('public.old_news', CREATE_OLD_NEWS, ('CREATE INDEX ix_old_news_published_at ON public.old_news(published_at)',)),
    ('public.news_location', CREATE_NEWS_LOCATION, ()),
    ('public.news_keywords', CREATE_NEWS_KEYWORDS, ('CREATE INDEX ix_news_keywords_keyword ON public.news_keywords(keyword_id)',)),
    ('public.news_embeddings', CREATE_NEWS_EMBEDDINGS, ()),
    ('public.news_embedding_locator', CREATE_NEWS_EMBEDDING_LOCATOR, ()),
    ('public.learning_data_news', CREATE_LEARNING_DATA_NEWS, ()),
    ('analysis.analysis_runs', CREATE_ANALYSIS_RUNS, ()),
    ('analysis.analysis_overview', CREATE_ANALYSIS_OVERVIEW, ()),
    ('analysis.analysis_keyword_stats', CREATE_ANALYSIS_KEYWORD_STATS, ()),
    ('analysis.analysis_category_stats', CREATE_ANALYSIS_CATEGORY_STATS, ()),
    ('analysis.analysis_publisher_stats', CREATE_ANALYSIS_PUBLISHER_STATS, ()),
    ('analysis.analysis_author_stats', CREATE_ANALYSIS_AUTHOR_STATS, ()),
    ('analysis.analysis_time_buckets', CREATE_ANALYSIS_TIME_BUCKETS, ()),
    ('analysis.analysis_issues', CREATE_ANALYSIS_ISSUES, ()),
    ('analysis.analysis_issue_members', CREATE_ANALYSIS_ISSUE_MEMBERS, ('CREATE INDEX ix_issue_members_news ON analysis.analysis_issue_members(news_id)',)),
    ('analysis.analysis_issue_keywords', CREATE_ANALYSIS_ISSUE_KEYWORDS, ()),
    ('analysis.analysis_issue_timeseries', CREATE_ANALYSIS_ISSUE_TIMESERIES, ()),
    ('analysis.analysis_similar_news', CREATE_ANALYSIS_SIMILAR_NEWS, ()),
)

@_logged
async def ensure_embedding_partitions(connection, years: Iterable[int]) -> None:
    """필요 연도를 명시해 호출. 과거/미래 기사 INSERT 전에 해당 연도를 준비한다."""
    years = tuple(years)
    if any(type(year) is not int or not 1 <= year <= 9998 for year in years):
        raise ValueError('파티션 연도는 1~9998 정수여야 합니다.')
    async with connection.transaction():
        await connection.execute('SELECT pg_advisory_xact_lock(736204185901)')
        for year in sorted(set(years)):
            name = f'public.news_embeddings_{year}'
            if await connection.fetchval('SELECT to_regclass($1)', name) is None:
                _LOGGER.info('연도 파티션 생성: %s', name)
                await connection.execute(f'''CREATE TABLE {name}
                    PARTITION OF public.news_embeddings
                    FOR VALUES FROM ({year}) TO ({year + 1})''')
            else:
                _LOGGER.info('기존 연도 파티션 확인: %s', name)
                attached = await connection.fetchval('''SELECT EXISTS (
                    SELECT 1 FROM pg_inherits WHERE inhrelid=to_regclass($1)
                    AND inhparent='public.news_embeddings'::regclass)''', name)
                if not attached:
                    raise RuntimeError(f'{name}은 임베딩 부모에 연결된 파티션이 아닙니다.')

async def check_vector_extension(connection) -> None:
    """DB에 확장을 만들기 전에 PostgreSQL 서버의 설치 가능 목록을 확인한다."""
    available = await connection.fetchval(
        "SELECT EXISTS (SELECT 1 FROM pg_available_extensions WHERE name='vector')"
    )
    if not available:
        version = await connection.fetchval('SHOW server_version')
        raise RuntimeError(
            f'접속한 PostgreSQL {version} 서버에서 pgvector 확장 설치 파일을 찾지 못했습니다.\n'
            'Python의 pip install pgvector와 별도로 PostgreSQL 서버용 확장을 설치해야 합니다.\n'
            '서버와 같은 PostgreSQL 버전/아키텍처용 pgvector를 설치한 뒤 다시 실행하세요.\n'
            'Windows 설치 안내: https://github.com/pgvector/pgvector#windows'
        )


@_logged
async def step_3_prepare_tables(connection, years: Iterable[int]) -> None:
    """3. 누락 테이블 생성 및 원본 URL 스키마로 전환."""
    await check_vector_extension(connection)
    async with connection.transaction():
        from ..table_manager import NEWS_WRITE_LOCK
        await connection.execute('SELECT pg_advisory_xact_lock($1)', NEWS_WRITE_LOCK)
        await connection.execute('SELECT pg_advisory_xact_lock(736204185901)')
        await connection.execute('CREATE SCHEMA IF NOT EXISTS analysis')
        _LOGGER.info('pgvector 확장 확인 및 필요 시 생성')
        await connection.execute('CREATE EXTENSION IF NOT EXISTS vector WITH SCHEMA public')
        if await connection.fetchval("SELECT to_regtype('public.halfvec')") is None:
            raise RuntimeError('public 스키마에 pgvector >= 0.7의 halfvec 타입이 필요합니다.')
        for name, create_sql, indexes in TABLE_DEFINITIONS:
            if await connection.fetchval('SELECT to_regclass($1)', name) is None:
                _LOGGER.info('3.1 누락 테이블 생성: %s', name)
                await connection.execute(create_sql)
                for index in indexes:
                    _LOGGER.info('인덱스 생성: %s', index)
                    await connection.execute(index)
            else:
                _LOGGER.info('3.2 기존 테이블 사용: %s', name)
        await migrate_author_email(connection)
        await migrate_original_urls(connection)
        await ensure_embedding_partitions(connection, years)

async def migrate_author_email(connection) -> None:
    """기존 기사를 유지하며 세 본문 테이블에 선택적 작성자 이메일 컬럼을 추가한다."""
    from ..table_manager import NEWS_WRITE_LOCK
    async with connection.transaction():
        await connection.execute('SELECT pg_advisory_xact_lock($1)', NEWS_WRITE_LOCK)
        for table in ('today_news', 'news', 'old_news'):
            await connection.execute(
                f'ALTER TABLE public.{table} ADD COLUMN IF NOT EXISTS author_email TEXT'
            )
            await connection.execute(
                f"ALTER TABLE public.{table} ADD COLUMN IF NOT EXISTS author_contacts JSONB NOT NULL DEFAULT '[]'::jsonb"
            )


async def validate_schema(connection) -> None:
    """구형 동명 테이블을 감지한다. 기존 데이터를 자동 변경/삭제하지 않는다."""
    import re
    for table, ddl, _ in TABLE_DEFINITIONS:
        expected = set(re.findall(
            r'^\s*([a-z_][a-z_0-9]*)\s+(?:BIGINT|SMALLINT|INTEGER|TEXT|VARCHAR|BYTEA|TIMESTAMPTZ|DOUBLE|JSONB|public\.halfvec)\b',
            ddl, flags=re.MULTILINE,
        ))
        actual = {row['attname'] for row in await connection.fetch(
            'SELECT attname FROM pg_attribute WHERE attrelid=to_regclass($1) '
            'AND attnum > 0 AND NOT attisdropped', table
        )}
        missing = expected - actual
        if missing:
            raise RuntimeError(f'{table}: 필수 열 {sorted(missing)} 누락. 기존 DB 스키마 마이그레이션이 필요합니다.')


async def migrate_original_urls(connection) -> None:
    """기존 뉴스의 URL은 유지하고 폐기된 컬럼을 트랜잭션 안에서 제거한다."""
    from ..table_manager import NEWS_WRITE_LOCK
    async with connection.transaction():
        await connection.execute('SELECT pg_advisory_xact_lock($1)', NEWS_WRITE_LOCK)
        legacy = await connection.fetchval("""SELECT EXISTS (
            SELECT 1 FROM information_schema.columns
            WHERE table_schema='public'
              AND table_name IN ('today_news','news','old_news')
              AND column_name IN ('canonical_url','canonical_url_hash'))""")
        index_exists = await connection.fetchval("SELECT to_regclass('public.uq_today_news_url')")
        if not legacy and index_exists is not None:
            return
        await connection.execute('LOCK TABLE public.today_news, public.news, public.old_news IN ACCESS EXCLUSIVE MODE')
        if await connection.fetchval("""SELECT EXISTS (
            SELECT 1 FROM public.today_news GROUP BY url HAVING count(*) > 1)"""):
            raise RuntimeError('today_news에 동일한 원본 URL이 여러 건 있습니다. 중복 기사를 확인한 뒤 다시 연결하세요. DB 변경은 취소됩니다.')
        await connection.execute('CREATE UNIQUE INDEX IF NOT EXISTS uq_today_news_url ON public.today_news(url)')
        for table in ('today_news', 'news', 'old_news'):
            await connection.execute(f'ALTER TABLE public.{table} DROP COLUMN IF EXISTS canonical_url, DROP COLUMN IF EXISTS canonical_url_hash')
        _LOGGER.info('원본 URL 비교 스키마 전환 완료')