"""뉴스와 분석 결과 저장 기능."""
from __future__ import annotations

import json
import math
from dataclasses import dataclass
from datetime import datetime, timezone

from ..connection import ensure_embedding_partitions, validate_url
from ..news_archive import NEWS_COLUMNS, NEWS_WRITE_LOCK

@dataclass(frozen=True)
class SaveResult:
    news_id: int
    created: bool

def _aware(value: datetime, name: str = "published_at") -> datetime:
    if not isinstance(value, datetime) or value.utcoffset() is None:
        raise ValueError(f"{name}에는 시간대가 있는 datetime이 필요합니다.")
    return value

async def _publisher_id(connection, publisher_name: str) -> int:
    if not isinstance(publisher_name, str) or not publisher_name.strip() or len(publisher_name.strip()) > 100:
        raise ValueError("언론사 이름은 1~100자여야 합니다.")
    return await connection.fetchval(
        """INSERT INTO public.publishers(name) VALUES($1)
           ON CONFLICT(name) DO UPDATE SET name=EXCLUDED.name RETURNING id""",
        publisher_name.strip(),
    )

async def save_category(connection, name: str, parent_id: int | None = None) -> int:
    """카테고리를 재사용하고, 없으면 만든 뒤 id를 반환한다."""
    if not isinstance(name, str) or not name.strip() or len(name.strip()) > 20:
        raise ValueError("카테고리 이름은 1~20자여야 합니다.")
    async with connection.transaction():
        await connection.execute(
            """INSERT INTO public.categories(name,parent_id) VALUES($1,$2)
               ON CONFLICT DO NOTHING""", name.strip(), parent_id,
        )
        return await connection.fetchval(
            """SELECT id FROM public.categories
               WHERE name=$1 AND parent_id IS NOT DISTINCT FROM $2::bigint""",
            name.strip(), parent_id,
        )

def _validate_keywords(keywords):
    rows, seen_words, seen_ranks = [], set(), set()
    for item in keywords:
        word = item["keyword"]
        score = float(item["score"])
        rank = item["rank"]
        if not isinstance(word, str) or not word.strip() or len(word.strip()) > 50:
            raise ValueError("키워드는 1~50자여야 합니다.")
        word = word.strip()
        if not math.isfinite(score) or score < 0 or type(rank) is not int or rank < 1:
            raise ValueError("키워드 점수는 유한한 0 이상, 순위는 양의 정수여야 합니다.")
        if word in seen_words or rank in seen_ranks:
            raise ValueError("한 기사에 키워드와 순위를 중복 지정할 수 없습니다.")
        seen_words.add(word)
        seen_ranks.add(rank)
        rows.append((word, score, rank))
    return rows

async def _replace_keywords(connection, news_id: int, rows) -> None:
    await connection.execute("DELETE FROM public.news_keywords WHERE news_id=$1", news_id)
    for word, score, rank in rows:
        keyword_id = await connection.fetchval(
            """INSERT INTO public.keywords(keyword) VALUES($1)
               ON CONFLICT(keyword) DO UPDATE SET keyword=EXCLUDED.keyword RETURNING id""",
            word,
        )
        await connection.execute(
            """INSERT INTO public.news_keywords
               (news_id,keyword_id,keyword_score,keyword_rank) VALUES($1,$2,$3,$4)""",
            news_id, keyword_id, score, rank,
        )

async def save_keywords(connection, news_id: int, keywords) -> None:
    """기사 키워드 전체를 교체한다. 빈 목록은 연결만 삭제한다."""
    rows = _validate_keywords(keywords)
    async with connection.transaction():
        if await connection.fetchval("SELECT id FROM public.news_id WHERE id=$1 FOR UPDATE", news_id) is None:
            raise ValueError("존재하지 않는 news_id입니다.")
        await _replace_keywords(connection, news_id, rows)

async def _save_embedding(connection, news_id: int, model_name: str, embedding) -> int:
    values = [float(value) for value in embedding]
    if not values or any(not math.isfinite(v) or abs(v) > 65504 for v in values) or not any(values):
        raise ValueError("임베딩은 halfvec 범위 내의 유한한 0이 아닌 벡터여야 합니다.")
    if not isinstance(model_name, str) or not model_name.strip() or len(model_name.strip()) > 100:
        raise ValueError("임베딩 모델 이름은 1~100자여야 합니다.")
    published_at = await connection.fetchval(
        """SELECT published_at FROM public.today_news WHERE news_id=$1
           UNION ALL SELECT published_at FROM public.news WHERE news_id=$1
           UNION ALL SELECT published_at FROM public.old_news WHERE news_id=$1""", news_id,
    )
    if published_at is None:
        raise ValueError("발행시각이 있는 기사 본문이 필요합니다.")
    year = published_at.astimezone(timezone.utc).year
    await ensure_embedding_partitions(connection, [year])
    await connection.execute(
        """INSERT INTO public.embedding_models(model_name,dimension) VALUES($1,$2)
           ON CONFLICT(model_name) DO NOTHING""", model_name.strip(), len(values),
    )
    model = await connection.fetchrow(
        "SELECT id,dimension FROM public.embedding_models WHERE model_name=$1", model_name.strip(),
    )
    if model["dimension"] != len(values):
        raise ValueError("기존 모델에 등록된 임베딩 차원과 입력 차원이 다릅니다.")
    previous_year = await connection.fetchval(
        "SELECT embedding_year FROM public.news_embedding_locator WHERE news_id=$1 AND model_id=$2",
        news_id, model["id"],
    )
    if previous_year is not None and previous_year != year:
        await connection.execute(
            """DELETE FROM public.news_embeddings
               WHERE news_id=$1 AND model_id=$2 AND embedding_year=$3""",
            news_id, model["id"], previous_year,
        )
    await connection.execute(
        """INSERT INTO public.news_embeddings(news_id,model_id,embedding_year,embedding)
           VALUES($1,$2,$3,$4::text::public.halfvec)
           ON CONFLICT(news_id,model_id,embedding_year)
           DO UPDATE SET embedding=EXCLUDED.embedding""",
        news_id, model["id"], year, json.dumps(values, allow_nan=False),
    )
    await connection.execute(
        """INSERT INTO public.news_embedding_locator(news_id,model_id,embedding_year)
           VALUES($1,$2,$3) ON CONFLICT(news_id,model_id)
           DO UPDATE SET embedding_year=EXCLUDED.embedding_year""",
        news_id, model["id"], year,
    )
    return model["id"]

async def save_embedding(connection, news_id: int, *, model_name: str, embedding) -> int:
    """기사 발행연도의 halfvec 파티션에 저장하고 locator를 갱신한다."""
    async with connection.transaction():
        await connection.execute("SELECT pg_advisory_xact_lock($1)", NEWS_WRITE_LOCK)
        if await connection.fetchval("SELECT id FROM public.news_id WHERE id=$1 FOR UPDATE", news_id) is None:
            raise ValueError("존재하지 않는 news_id입니다.")
        return await _save_embedding(connection, news_id, model_name, embedding)

def _news_labels(*, label1, label2, label1_id, label2_id, category_id):
    """문자열 라벨 또는 카테고리 ID 쌍을 검사한다. 동일한 두 라벨도 허용한다."""
    for name, value in (("label1_id", label1_id), ("label2_id", label2_id),
                        ("category_id", category_id)):
        if value is not None and (type(value) is not int or not 1 <= value <= 9223372036854775807):
            raise ValueError(f"{name}는 양의 BIGINT 정수 또는 None이어야 합니다.")
    names = []
    for name, value in (("label1", label1), ("label2", label2)):
        if value is not None:
            if not isinstance(value, str) or not 1 <= len(value.strip()) <= 20:
                raise ValueError(f"{name}은 1~20자 카테고리 이름이어야 합니다.")
            value = value.strip()
        names.append(value)
    label1, label2 = names
    if category_id is not None:
        if label1 is not None or (label1_id is not None and label1_id != category_id):
            raise ValueError("category_id와 첫 번째 라벨을 다르게 지정할 수 없습니다.")
        label1_id = category_id
    if (label1 is not None and label1_id is not None) or (label2 is not None and label2_id is not None):
        raise ValueError("같은 라벨의 이름과 ID를 동시에 지정하지 마세요.")
    first = label1 if label1 is not None else label1_id
    second = label2 if label2 is not None else label2_id
    legacy_only = category_id is not None and label1 is None and second is None
    if (first is None) != (second is None) and not legacy_only:
        raise ValueError("분류 결과는 label1·label2 또는 label1_id·label2_id 두 개를 전달해야 합니다.")
    return first, second


async def save_news(
    connection, *, publisher_name: str, title: str, url: str,
    published_at: datetime, content: str,
    author: str | None = None, category_id: int | None = None,
    label1: str | None = None, label2: str | None = None,
    label1_id: int | None = None, label2_id: int | None = None,
    author_email: str | None = None, author_contacts=None,
    keywords=None, model_name: str | None = None, embedding=None,
) -> SaveResult:
    """
    언론사, 영구 ID, 본문 단계, 위치 및 선택 부가 데이터를 한 트랜잭션에 저장.

    author_email은 선택값이다. 수집한 작성자 이메일을 전달하면 저장하며,
    생략하거나 빈 문자열을 전달하면 NULL로 저장한다.
    분류는 label1='정치', label2='경제' 또는 label1_id=1, label2_id=2로 전달한다.
    문자열은 save_category()와 동일하게 최상위 카테고리 이름으로 등록/재사용한다.
    하위 카테고리를 지정하려면 해당 ID 쌍을 전달한다. 같은 라벨 두 개도 허용한다.
    미분류는 두 값 모두 생략한다. 구형 category_id는 첫 라벨로 호환 저장한다.
    """
    _aware(published_at)
    first_label, second_label = _news_labels(
        label1=label1, label2=label2, label1_id=label1_id,
        label2_id=label2_id, category_id=category_id,
    )
    if not isinstance(title, str) or not title.strip() or not isinstance(content, str) or not content.strip():
        raise ValueError("기사 제목과 본문이 필요합니다.")
    if author is not None and (not isinstance(author, str) or len(author) > 100):
        raise ValueError("작성자는 100자 이하여야 합니다.")
    if author_email is not None:
        if not isinstance(author_email, str) or "\x00" in author_email:
            raise ValueError("작성자 이메일은 NUL 없는 문자열 또는 None이어야 합니다.")
        author_email = author_email.strip() or None
    contacts = [] if author_contacts is None else author_contacts
    if not isinstance(contacts, list) or any(
        not isinstance(item, dict) or set(item) != {"name", "email"}
        or not isinstance(item["name"], str) or not 1 <= len(item["name"]) <= 100
        or (item["email"] is not None and (
            not isinstance(item["email"], str) or "@" not in item["email"] or "\x00" in item["email"]))
        for item in contacts
    ):
        raise ValueError("작성자 연락처는 name 문자열과 email 문자열 또는 None의 목록이어야 합니다.")
    source_url = validate_url(url)
    keyword_rows = None if keywords is None else _validate_keywords(keywords)
    if (model_name is None) != (embedding is None):
        raise ValueError("임베딩 저장에는 model_name과 embedding을 함께 지정해야 합니다.")

    async with connection.transaction():
        await connection.execute("SELECT pg_advisory_xact_lock($1)", NEWS_WRITE_LOCK)
        duplicate = await connection.fetchrow(
            "SELECT news_id FROM public.today_news WHERE url=$1", source_url,
        )
        if duplicate:
            return SaveResult(duplicate["news_id"], False)

        label1_id = await save_category(connection, first_label) if isinstance(first_label, str) else first_label
        label2_id = await save_category(connection, second_label) if isinstance(second_label, str) else second_label
        publisher_id = await _publisher_id(connection, publisher_name)
        news_id = await connection.fetchval("INSERT INTO public.news_id DEFAULT VALUES RETURNING id")
        stage = await connection.fetchval(
            """SELECT CASE
                 WHEN $1::timestamptz >= CURRENT_TIMESTAMP-INTERVAL '24 hours' THEN 'today'
                 WHEN $1::timestamptz >= CURRENT_TIMESTAMP-INTERVAL '3 years' THEN 'news'
                 ELSE 'old' END""", published_at,
        )
        table = {"today": "today_news", "news": "news", "old": "old_news"}.get(stage)
        if table is None:
            raise RuntimeError(f"알 수 없는 본문 저장 단계: {stage!r}")
        columns = NEWS_COLUMNS
        values = [news_id, publisher_id, label1_id, label2_id, title.strip(), source_url,
                  published_at, author, author_email, content.strip(), json.dumps(contacts, ensure_ascii=False)]
        placeholders = ",".join(f"${i}" for i in range(1, len(values) + 1))
        await connection.execute(
            f"INSERT INTO public.{table}({columns}) VALUES({placeholders})", *values,
        )
        await connection.execute(
            "INSERT INTO public.news_location(news_id,storage_type) VALUES($1,$2)", news_id, stage,
        )
        if keyword_rows is not None:
            await _replace_keywords(connection, news_id, keyword_rows)
        if embedding is not None:
            await _save_embedding(connection, news_id, model_name, embedding)
        return SaveResult(news_id, True)

async def save_learning_data(connection, news_id: int, *, dataset_name: str,
                             dataset_version: str, data_split: str) -> None:
    if data_split not in ("train", "valid", "test"):
        raise ValueError("data_split은 train, valid, test 중 하나여야 합니다.")
    await connection.execute(
        """INSERT INTO public.learning_data_news
           (news_id,dataset_name,dataset_version,data_split) VALUES($1,$2,$3,$4)
           ON CONFLICT(news_id) DO UPDATE SET dataset_name=EXCLUDED.dataset_name,
             dataset_version=EXCLUDED.dataset_version,data_split=EXCLUDED.data_split""",
        news_id, dataset_name, dataset_version, data_split,
    )

ANALYSIS_TABLES = {
    "keyword_stats": ("analysis_keyword_stats", "keyword_id,news_count,score_sum,score_max,rank_sum,analysis_score,result_rank"),
    "category_stats": ("analysis_category_stats", "category_id,news_count"),
    "publisher_stats": ("analysis_publisher_stats", "publisher_id,news_count"),
    "author_stats": ("analysis_author_stats", "author_name,news_count"),
    "time_buckets": ("analysis_time_buckets", "bucket_start,bucket_end,news_count"),
    "similar_news": ("analysis_similar_news", "source_news_id,similar_news_id,similarity_score,similarity_rank"),
}

ISSUE_FIELDS = (
    "cluster_no,issue_name,representative_news_id,news_count,average_similarity,"
    "first_published_at,last_published_at,trend_label,trend_score"
)

ISSUE_CHILDREN = {
    "members": ("analysis_issue_members", "news_id,similarity_score,member_rank"),
    "keywords": ("analysis_issue_keywords", "keyword_id,keyword_score,keyword_rank"),
    "timeseries": ("analysis_issue_timeseries", "bucket_start,news_count,popularity_score"),
}

async def create_analysis_run(connection, *, period_start, period_end, bucket_unit,
                              embedding_model_id=None, filters=None,
                              algorithm_name="", algorithm_version="", request_hash=None) -> int:
    """분석 실행을 만들고, 같은 request_hash가 있으면 기존 실행 id를 돌려준다."""
    _aware(period_start, "period_start")
    _aware(period_end, "period_end")
    if period_start >= period_end or bucket_unit not in ("hour", "day", "week", "month"):
        raise ValueError("분석 기간 또는 bucket_unit이 올바르지 않습니다.")
    if request_hash is not None and not isinstance(request_hash, bytes):
        raise ValueError("request_hash는 bytes 또는 None이어야 합니다.")
    async with connection.transaction():
        new_id = await connection.fetchval(
            """INSERT INTO analysis.analysis_runs
               (period_start,period_end,bucket_unit,embedding_model_id,filters,
                algorithm_name,algorithm_version,request_hash,status)
               VALUES($1,$2,$3,$4,$5::jsonb,$6,$7,$8,'running')
               ON CONFLICT(request_hash) DO NOTHING RETURNING id""",
            period_start, period_end, bucket_unit, embedding_model_id,
            json.dumps(filters or {}, ensure_ascii=False), algorithm_name,
            algorithm_version, request_hash,
        )
        if new_id is not None:
            return new_id
        return await connection.fetchval(
            "SELECT id FROM analysis.analysis_runs WHERE request_hash=$1", request_hash,
        )

async def _insert_analysis_rows(connection, table, owner_column, owner_id, columns, rows):
    names = columns.split(",")
    for row in rows:
        if set(row) - set(names):
            raise ValueError(f"{table}에 정의되지 않은 열이 있습니다.")
        values = [owner_id] + [row.get(name) for name in names]
        slots = ",".join(f"${index}" for index in range(1, len(values) + 1))
        await connection.execute(
            f"INSERT INTO analysis.{table}({owner_column},{columns}) VALUES({slots})", *values,
        )

async def save_analysis_results(connection, analysis_id: int, results: dict) -> None:
    """
    분석 통계, 이슈, 이슈 구성원 및 추이를 원자적으로 저장한다.

    입력은 외부 분석기가 계산한 값이다. overview는 dict, 각 통계와 issues는
    list[dict]를 받으며 issue 항목에는 members/keywords/timeseries를 넣을 수 있다.
    """
    allowed = set(ANALYSIS_TABLES) | {"overview", "issues"}
    if not isinstance(results, dict) or set(results) - allowed:
        raise ValueError("지원하지 않는 분석 결과 키입니다.")
    async with connection.transaction():
        status = await connection.fetchval(
            "SELECT status FROM analysis.analysis_runs WHERE id=$1 FOR UPDATE", analysis_id,
        )
        if status != "running":
            raise ValueError("running 상태의 분석 실행만 결과를 기록할 수 있습니다.")
        if "overview" in results:
            overview_columns = "news_count,publisher_count,category_count,author_count,keyword_count,issue_count"
            await _insert_analysis_rows(
                connection, "analysis_overview", "analysis_id", analysis_id,
                overview_columns, [results["overview"]],
            )
        for key, (table, columns) in ANALYSIS_TABLES.items():
            if key in results:
                await _insert_analysis_rows(
                    connection, table, "analysis_id", analysis_id, columns, results[key],
                )
        for issue in results.get("issues", []):
            allowed_issue_keys = set(ISSUE_FIELDS.split(",")) | set(ISSUE_CHILDREN)
            if set(issue) - allowed_issue_keys:
                raise ValueError("지원하지 않는 이슈 결과 열입니다.")
            fields = ISSUE_FIELDS.split(",")
            args = [analysis_id] + [issue.get(field) for field in fields]
            slots = ",".join(f"${index}" for index in range(1, len(args) + 1))
            issue_id = await connection.fetchval(
                f"INSERT INTO analysis.analysis_issues(analysis_id,{ISSUE_FIELDS}) "
                f"VALUES({slots}) RETURNING id", *args,
            )
            for key, (table, columns) in ISSUE_CHILDREN.items():
                await _insert_analysis_rows(
                    connection, table, "issue_id", issue_id, columns, issue.get(key, []),
                )
        await connection.execute(
            """UPDATE analysis.analysis_runs SET status='completed',
               completed_at=CURRENT_TIMESTAMP WHERE id=$1""", analysis_id,
        )

async def mark_analysis_failed(connection, analysis_id: int) -> None:
    await connection.execute(
        """UPDATE analysis.analysis_runs SET status='failed',completed_at=CURRENT_TIMESTAMP
           WHERE id=$1 AND status='running'""", analysis_id,
    )