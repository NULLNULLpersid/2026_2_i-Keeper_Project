"""기사 본문 저장 단계와 테이블 수명주기 관리."""
from __future__ import annotations

NEWS_WRITE_LOCK = 736204185903
NEWS_COLUMNS = (
    "news_id,publisher_id,category_id,title,url,"
    "published_at,author,author_email,content,author_contacts"
)
NEWS_UNION = " UNION ALL ".join(
    f"SELECT {NEWS_COLUMNS},'{stage}'::text AS storage_type FROM public.{table}"
    for table, stage in (("today_news", "today"), ("news", "news"), ("old_news", "old"))
)

async def archive_news(connection, *, batch_size: int = 1000) -> dict[str, int]:
    """24시간 지난 기사를 news로, 3년 지난 기사를 old_news로 이동.

    이동은 published_at 기준이다. 한 번 호출할 때 각 단계에서 batch_size만큼
    이동하므로 대량 적체는 반환 건수가 0이 될 때까지 반복 호출하면 된다.
    news_id, 키워드, 임베딩, 학습 데이터는 그대로 유지된다.
    """
    if type(batch_size) is not int or batch_size < 1:
        raise ValueError("batch_size는 양의 정수여야 합니다.")
    results: dict[str, int] = {}
    async with connection.transaction():
        await connection.execute("SELECT pg_advisory_xact_lock($1)", NEWS_WRITE_LOCK)
        for source, destination, stage, age in (
            ("today_news", "news", "news", "24 hours"),
            ("news", "old_news", "old", "3 years"),
        ):
            moved = await connection.fetch(
                f"""WITH candidates AS (
                       SELECT news_id FROM public.{source}
                       WHERE published_at < CURRENT_TIMESTAMP-INTERVAL '{age}'
                       ORDER BY published_at,news_id
                       LIMIT $1 FOR UPDATE SKIP LOCKED
                   ), deleted AS (
                       DELETE FROM public.{source}
                       WHERE news_id IN (SELECT news_id FROM candidates)
                       RETURNING {NEWS_COLUMNS}
                   )
                   INSERT INTO public.{destination}({NEWS_COLUMNS})
                   SELECT {NEWS_COLUMNS} FROM deleted
                   RETURNING news_id""", batch_size,
            )
            ids = [row["news_id"] for row in moved]
            if ids:
                await connection.execute(
                    """INSERT INTO public.news_location(news_id,storage_type)
                       SELECT unnest($1::bigint[]),$2::varchar
                       ON CONFLICT(news_id) DO UPDATE SET storage_type=EXCLUDED.storage_type""",
                    ids, stage,
                )
            results[source] = len(ids)
    return results
