"""뉴스와 분석 결과 조회 기능."""
from __future__ import annotations

import json
from datetime import datetime

from ..setting import validate_url
from .save import ANALYSIS_TABLES, ISSUE_CHILDREN, _aware
from ..table_manager import NEWS_UNION

async def get_existing_urls(connection, urls) -> set[str]:
    """24시간 중복 검사 대상인 today_news에서 URL을 찾는다."""
    original_urls = {validate_url(url) for url in urls}
    if not original_urls:
        return set()
    rows = await connection.fetch(
        """SELECT url FROM public.today_news
           WHERE url=ANY($1::text[])""",
        list(original_urls),
    )
    return {row["url"] for row in rows}

async def get_last_news_time(connection, publisher_name: str):
    return await connection.fetchval(
        f"""SELECT max(n.published_at) FROM ({NEWS_UNION}) n
            JOIN public.publishers p ON p.id=n.publisher_id WHERE p.name=$1""",
        publisher_name,
    )

async def get_news(connection, news_id: int):
    row = await connection.fetchrow(
        f"""SELECT n.*,p.name AS publisher_name FROM ({NEWS_UNION}) n
            LEFT JOIN public.publishers p ON p.id=n.publisher_id WHERE n.news_id=$1""",
        news_id,
    )
    return dict(row) if row else None

async def list_news(connection, *, start=None, end=None, publisher_id=None,
                    category_id=None, author=None, limit=100, offset=0):
    if type(limit) is not int or not 1 <= limit <= 10000 or type(offset) is not int or offset < 0:
        raise ValueError("limit은 1~10000, offset은 0 이상의 정수여야 합니다.")
    if start is not None:
        _aware(start, "start")
    if end is not None:
        _aware(end, "end")
    if start is not None and end is not None and start >= end:
        raise ValueError("start는 end보다 빨라야 합니다.")
    rows = await connection.fetch(
        f"""SELECT n.*,p.name AS publisher_name FROM ({NEWS_UNION}) n
            LEFT JOIN public.publishers p ON p.id=n.publisher_id
            WHERE ($1::timestamptz IS NULL OR n.published_at >= $1)
              AND ($2::timestamptz IS NULL OR n.published_at < $2)
              AND ($3::bigint IS NULL OR n.publisher_id=$3)
              AND ($4::bigint IS NULL OR n.category_id=$4)
              AND ($5::text IS NULL OR n.author=$5)
            ORDER BY n.published_at DESC,n.news_id DESC LIMIT $6 OFFSET $7""",
        start, end, publisher_id, category_id, author, limit, offset,
    )
    return [dict(row) for row in rows]

async def get_keywords(connection, news_id: int):
    rows = await connection.fetch(
        """SELECT k.id AS keyword_id,k.keyword,nk.keyword_score,nk.keyword_rank
           FROM public.news_keywords nk JOIN public.keywords k ON k.id=nk.keyword_id
           WHERE nk.news_id=$1 ORDER BY nk.keyword_rank""", news_id,
    )
    return [dict(row) for row in rows]

async def get_embedding(connection, news_id: int, model_id: int):
    row = await connection.fetchrow(
        """SELECT e.news_id,e.model_id,e.embedding_year,e.embedding::text AS embedding,
                  m.model_name,m.dimension
           FROM public.news_embedding_locator l JOIN public.news_embeddings e
             ON (e.news_id,e.model_id,e.embedding_year)=(l.news_id,l.model_id,l.embedding_year)
           JOIN public.embedding_models m ON m.id=e.model_id
           WHERE l.news_id=$1 AND l.model_id=$2""", news_id, model_id,
    )
    if row is None:
        return None
    result = dict(row)
    result["embedding"] = json.loads(result["embedding"]) if result["embedding"] else None
    return result

async def find_similar_news(connection, news_id: int, model_id: int, *, limit=20):
    """같은 모델의 임베딩만 비교해 코사인 유사 뉴스 목록을 반환한다."""
    if type(limit) is not int or not 1 <= limit <= 10000:
        raise ValueError("limit은 1~10000 정수여야 합니다.")
    source = await get_embedding(connection, news_id, model_id)
    if source is None or source["embedding"] is None:
        return []
    rows = await connection.fetch(
        """SELECT e.news_id,1-(e.embedding <=> $3::text::public.halfvec) AS similarity_score
           FROM public.news_embeddings e
           JOIN public.news_embedding_locator l
             ON (e.news_id,e.model_id,e.embedding_year)=(l.news_id,l.model_id,l.embedding_year)
           WHERE e.model_id=$2 AND e.news_id<>$1 AND e.embedding IS NOT NULL
           ORDER BY similarity_score DESC,e.news_id LIMIT $4""",
        news_id, model_id, json.dumps(source["embedding"]), limit,
    )
    return [dict(row) for row in rows]

async def get_analysis_results(connection, analysis_id: int):
    """분석 실행과 통계·이슈 하위 데이터를 하나의 읽기 스냅샷으로 돌려준다."""
    async with connection.transaction(isolation="repeatable_read", readonly=True):
        run = await connection.fetchrow(
            "SELECT * FROM analysis.analysis_runs WHERE id=$1", analysis_id,
        )
        if run is None:
            return None
        result = {"run": dict(run)}
        if isinstance(result["run"].get("filters"), str):
            result["run"]["filters"] = json.loads(result["run"]["filters"])
        for key, (table, _) in ANALYSIS_TABLES.items():
            result[key] = [dict(row) for row in await connection.fetch(
                f"SELECT * FROM analysis.{table} WHERE analysis_id=$1", analysis_id,
            )]
        overview = await connection.fetchrow(
            "SELECT * FROM analysis.analysis_overview WHERE analysis_id=$1", analysis_id,
        )
        result["overview"] = dict(overview) if overview else None
        issues = await connection.fetch(
            "SELECT * FROM analysis.analysis_issues WHERE analysis_id=$1 ORDER BY cluster_no", analysis_id,
        )
        result["issues"] = []
        for row in issues:
            issue = dict(row)
            for key, (table, _) in ISSUE_CHILDREN.items():
                issue[key] = [dict(child) for child in await connection.fetch(
                    f"SELECT * FROM analysis.{table} WHERE issue_id=$1", issue["id"],
                )]
            result["issues"].append(issue)
        return result
