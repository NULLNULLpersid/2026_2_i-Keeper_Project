"""DB 테이블과 인덱스의 구조 정의. DB 연결이나 SQL 실행은 하지 않는다."""
from __future__ import annotations

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

    label1_id BIGINT
        REFERENCES public.categories(id),

    label2_id BIGINT
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

    label1_id BIGINT
        REFERENCES public.categories(id),

    label2_id BIGINT
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

    label1_id BIGINT
        REFERENCES public.categories(id),

    label2_id BIGINT
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
    ("public.news_id", CREATE_NEWS_ID, ()),
    ("public.publishers", CREATE_PUBLISHERS, ()),
    ("public.categories", CREATE_CATEGORIES, ("CREATE UNIQUE INDEX uq_categories_root_name ON public.categories(name) WHERE parent_id IS NULL",)),
    ("public.keywords", CREATE_KEYWORDS, ()),
    ("public.embedding_models", CREATE_EMBEDDING_MODELS, ()),
    ("public.today_news", CREATE_TODAY_NEWS, ("CREATE INDEX ix_today_news_published_at ON public.today_news(published_at)", "CREATE UNIQUE INDEX uq_today_news_url ON public.today_news(url)")),
    ("public.news", CREATE_NEWS, ("CREATE INDEX ix_news_published_at ON public.news(published_at)",)),
    ("public.old_news", CREATE_OLD_NEWS, ("CREATE INDEX ix_old_news_published_at ON public.old_news(published_at)",)),
    ("public.news_location", CREATE_NEWS_LOCATION, ()),
    ("public.news_keywords", CREATE_NEWS_KEYWORDS, ("CREATE INDEX ix_news_keywords_keyword ON public.news_keywords(keyword_id)",)),
    ("public.news_embeddings", CREATE_NEWS_EMBEDDINGS, ()),
    ("public.news_embedding_locator", CREATE_NEWS_EMBEDDING_LOCATOR, ()),
    ("public.learning_data_news", CREATE_LEARNING_DATA_NEWS, ()),
    ("analysis.analysis_runs", CREATE_ANALYSIS_RUNS, ()),
    ("analysis.analysis_overview", CREATE_ANALYSIS_OVERVIEW, ()),
    ("analysis.analysis_keyword_stats", CREATE_ANALYSIS_KEYWORD_STATS, ()),
    ("analysis.analysis_category_stats", CREATE_ANALYSIS_CATEGORY_STATS, ()),
    ("analysis.analysis_publisher_stats", CREATE_ANALYSIS_PUBLISHER_STATS, ()),
    ("analysis.analysis_author_stats", CREATE_ANALYSIS_AUTHOR_STATS, ()),
    ("analysis.analysis_time_buckets", CREATE_ANALYSIS_TIME_BUCKETS, ()),
    ("analysis.analysis_issues", CREATE_ANALYSIS_ISSUES, ()),
    ("analysis.analysis_issue_members", CREATE_ANALYSIS_ISSUE_MEMBERS, ("CREATE INDEX ix_issue_members_news ON analysis.analysis_issue_members(news_id)",)),
    ("analysis.analysis_issue_keywords", CREATE_ANALYSIS_ISSUE_KEYWORDS, ()),
    ("analysis.analysis_issue_timeseries", CREATE_ANALYSIS_ISSUE_TIMESERIES, ()),
    ("analysis.analysis_similar_news", CREATE_ANALYSIS_SIMILAR_NEWS, ()),
)