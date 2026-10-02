from __future__ import annotations

import asyncio
import logging
import inspect
import threading
from contextvars import ContextVar
from functools import wraps
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
from datetime import datetime, timezone
from typing import Iterable

# db.log는 이 모듈과 같은 폴더에 UTF-8로 누적 저장한다.
# 로깅 파일을 열 수 없으면 예외를 전달하고 DB 작업을 시작하지 않는다.
LOG_PATH = Path(__file__).resolve().with_name("db.log")
_LOGGER = logging.getLogger(__name__ + ".database")
_LOGGER.setLevel(logging.INFO)
_LOGGER.propagate = False
_LOG_LOCK = threading.Lock()
_LOG_PASSWORD = ContextVar("db_log_password", default="")


class _PrivateFormatter(logging.Formatter):
    def format(self, record):
        rendered = super().format(record)
        password = _LOG_PASSWORD.get()
        return rendered.replace(password, "[REDACTED]") if password else rendered


def _configure_logging():
    with _LOG_LOCK:
        if not _LOGGER.handlers:
            handler = logging.FileHandler(LOG_PATH, mode="a", encoding="utf-8")
            handler.setFormatter(_PrivateFormatter(
                "%(asctime)s | %(levelname)s | %(threadName)s | %(message)s"
            ))
            _LOGGER.addHandler(handler)
    return _LOGGER


def _logged(function):
    """실행 시작/완료/오류 기록. 인수는 기록하지 않고 원래 예외를 전달한다."""
    signature = inspect.signature(function)

    def begin(args, kwargs):
        logger = _configure_logging()
        values = signature.bind_partial(*args, **kwargs).arguments
        token = _LOG_PASSWORD.set(values.get("password", _LOG_PASSWORD.get()))
        logger.info("실행 시작: %s", function.__name__)
        return logger, token

    if inspect.iscoroutinefunction(function):
        @wraps(function)
        async def asynchronous(*args, **kwargs):
            logger, token = begin(args, kwargs)
            try:
                result = await function(*args, **kwargs)
                logger.info("실행 완료: %s", function.__name__)
                return result
            except BaseException:
                logger.exception("실행 오류: %s", function.__name__)
                raise
            finally:
                _LOG_PASSWORD.reset(token)
        return asynchronous

    @wraps(function)
    def synchronous(*args, **kwargs):
        logger, token = begin(args, kwargs)
        try:
            result = function(*args, **kwargs)
            logger.info("실행 완료: %s", function.__name__)
            return result
        except BaseException:
            logger.exception("실행 오류: %s", function.__name__)
            raise
        finally:
            _LOG_PASSWORD.reset(token)
    return synchronous


# ============================================================================
# 공통 실행 도구
# ============================================================================

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


# ============================================================================
# 1. PostgreSQL 서버 경로 확인 및 생성
# ============================================================================

@_logged
def step_1_prepare_server(storage_path: str | Path, user: str, password: str,
                     bin_path: str | Path | None) -> Path:
    """1. 물리 경로 확인. 없는 경우에만 initdb 실행."""
    base = Path(storage_path).expanduser().resolve()
    data = base if (base / 'PG_VERSION').is_file() else base / 'News_Data_Server'
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


# ============================================================================
# 2. PostgreSQL 서버 상태 확인 및 접속
# ============================================================================

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


# ============================================================================
# 3. 필요한 테이블 확인 및 생성 — 테이블별 SQL
# ============================================================================

# public.news_id
CREATE_NEWS_ID = """
CREATE TABLE public.news_id (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY
);
"""

# public.publishers
CREATE_PUBLISHERS = """
CREATE TABLE public.publishers (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,

    name VARCHAR(100) NOT NULL UNIQUE
);
"""

# public.categories
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

# public.keywords
CREATE_KEYWORDS = """
CREATE TABLE public.keywords (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,

    keyword VARCHAR(50) NOT NULL UNIQUE
);
"""

# public.embedding_models
CREATE_EMBEDDING_MODELS = """
CREATE TABLE public.embedding_models (
    id SMALLINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,

    model_name VARCHAR(100) NOT NULL UNIQUE,

    dimension INTEGER NOT NULL CHECK(dimension > 0)
);
"""

# public.today_news
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

    canonical_url TEXT NOT NULL,

    canonical_url_hash BYTEA NOT NULL,

    published_at TIMESTAMPTZ NOT NULL,

    author VARCHAR(100),

    content TEXT NOT NULL
);
"""

# public.news
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

    canonical_url TEXT,

    published_at TIMESTAMPTZ,

    author VARCHAR(100),

    content TEXT
);
"""

# public.old_news
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

    canonical_url TEXT,

    published_at TIMESTAMPTZ,

    author VARCHAR(100),

    content TEXT
);
"""

# public.news_location
CREATE_NEWS_LOCATION = """
CREATE TABLE public.news_location (
    news_id BIGINT PRIMARY KEY
        REFERENCES public.news_id(id),

    storage_type VARCHAR CHECK(storage_type IN ('today', 'news', 'old'))
);
"""

# public.news_keywords
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

# public.news_embeddings
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

# public.news_embedding_locator
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

# public.learning_data_news
CREATE_LEARNING_DATA_NEWS = """
CREATE TABLE public.learning_data_news (
    news_id BIGINT PRIMARY KEY
        REFERENCES public.news_id(id),

    dataset_name VARCHAR,

    dataset_version VARCHAR,

    data_split VARCHAR CHECK(data_split IN ('train', 'valid', 'test'))
);
"""

# analysis.analysis_runs
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

# analysis.analysis_overview
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

# analysis.analysis_keyword_stats
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

# analysis.analysis_category_stats
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

# analysis.analysis_publisher_stats
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

# analysis.analysis_author_stats
CREATE_ANALYSIS_AUTHOR_STATS = """
CREATE TABLE analysis.analysis_author_stats (
    analysis_id BIGINT
        REFERENCES analysis.analysis_runs(id),

    author_name VARCHAR(100),

    news_count BIGINT,

    PRIMARY KEY(analysis_id, author_name)
);
"""

# analysis.analysis_time_buckets
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

# analysis.analysis_issues
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

# analysis.analysis_issue_members
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

# analysis.analysis_issue_keywords
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

# analysis.analysis_issue_timeseries
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

# analysis.analysis_similar_news
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


# 외래키 참조 순서에 따른 생성 목록. 기존 테이블은 변경하지 않는다.
TABLE_DEFINITIONS = (
    ('public.news_id', CREATE_NEWS_ID, ()),
    ('public.publishers', CREATE_PUBLISHERS, ()),
    ('public.categories', CREATE_CATEGORIES, ('CREATE UNIQUE INDEX uq_categories_root_name ON public.categories(name) WHERE parent_id IS NULL',)),
    ('public.keywords', CREATE_KEYWORDS, ()),
    ('public.embedding_models', CREATE_EMBEDDING_MODELS, ()),
    ('public.today_news', CREATE_TODAY_NEWS, ('CREATE INDEX ix_today_news_published_at ON public.today_news(published_at)', 'CREATE UNIQUE INDEX uq_today_news_url_hash ON public.today_news(canonical_url_hash)')),
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


@_logged
async def step_3_prepare_tables(connection, years: Iterable[int]) -> None:
    """3. 없는 테이블만 생성. 기존 테이블의 컬럼/제약은 수정하지 않는다."""
    async with connection.transaction():
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
        await ensure_embedding_partitions(connection, years)


# ============================================================================
# 실행 진입점
# ============================================================================

@_logged
async def connect_news_database(*, storage_path: str | Path, user: str,
                                password: str, host: str = '127.0.0.1',
                                port: int = 5432, database: str = 'News_Data_Server',
                                bin_path: str | Path | None = None,
                                embedding_years: Iterable[int] | None = None,
                                timeout: int = 30):
    """이미 입력받은 값을 사용하여 1→2→3 순서 실행, 열린 연결 반환.

    bin_path: initdb/pg_ctl이 있는 PostgreSQL 설치 bin 폴더. PATH에 있으면 생략.
    신규 서버는 loopback에서만 수신한다. 원격 서버 기동은 지원하지 않는다.
    인증 실패를 서버 중지로 오판하지 않으며 실행 중 서버를 재시작하지 않는다.
    기존 테이블의 스키마 마이그레이션/자동 복구는 하지 않는다.
    """
    from pgvector.asyncpg import register_vector

    if host not in ('localhost', '127.0.0.1', '::1'):
        raise ValueError('물리 경로를 관리하는 이 함수는 로컬 PostgreSQL 서버 전용입니다.')
    if not user or not password or any(ch in password for ch in '\r\n\x00'):
        raise ValueError('사용자/암호가 필요하며 암호에 줄바꿈 또는 NUL을 넣을 수 없습니다.')
    if type(port) is not int or not 1 <= port <= 65535 or timeout < 1:
        raise ValueError('port 또는 timeout 값이 올바르지 않습니다.')
    if not database or '\x00' in database or len(database.encode('utf-8')) > 63:
        raise ValueError('데이터베이스 이름은 1~63 UTF-8 바이트여야 합니다.')
    years = tuple(embedding_years) if embedding_years is not None else tuple(
        range(2025, datetime.now(timezone.utc).year + 2))
    if any(type(year) is not int or not 1 <= year <= 9998 for year in years):
        raise ValueError('embedding_years에는 1~9998 정수만 지정하세요.')
    
    # 1. 서버 경로 확인: 없으면 생성, 있으면 기존 클러스터 사용.
    data = await asyncio.to_thread(
        step_1_prepare_server, storage_path, user, password, bin_path
    )

    # 2. 서버 상태 확인: 열려 있으면 접속, 닫혀 있으면 가동 후 접속.
    connection = await step_2_connect_server(
        data=data, user=user, password=password, host=host, port=port,
        database=database, bin_path=bin_path, timeout=timeout,
    )

    try:
        # 3. 테이블 확인: 없는 테이블만 생성하고 기존 테이블 사용.
        await step_3_prepare_tables(connection, years)
        _LOGGER.info('Python pgvector 타입 연결 등록')
        await register_vector(connection, schema='public')
        return connection
    except BaseException:
        await connection.close()
        raise
