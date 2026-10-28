"""RSS → 중복 검사 → URL → 후속 처리 → DB 저장 순서를 실행한다."""
import aiohttp
import db as db_manager
from . import rss_reader, duplicate_check, article_reader
from ..data_processing import process_article
from ..media_rss_reader import get_reader


async def collect_with_connection(connection, urls, ui_callback, file_logger):
    """RSS 임시 저장 → 전체 중복 제거 → 기사 순차 수집 → DB 저장."""
    stats = dict(saved=0, duplicates=0, skipped=0, failed=0)
    if not urls:
        ui_callback('선택된 RSS 피드가 없습니다.')
        return stats
    latest = {}
    await db_manager.archive_news(connection)
    for info in urls:
        publisher = get_reader(info['media_name']).PUBLISHER_NAME
        if publisher not in latest:
            latest[publisher] = await rss_reader.get_saved_time(connection, publisher)
    seen_urls = set()
    async with aiohttp.ClientSession(headers={'User-Agent': rss_reader.USER_AGENT}) as session:
        temporary_items = []
        feeds = await rss_reader.read_selected_feeds(session, urls, latest)
        for info, items in zip(urls, feeds):
            publisher = get_reader(info['media_name']).PUBLISHER_NAME
            if isinstance(items, Exception):
                stats['failed'] += 1
                file_logger.error('[%s] RSS 실패: %s', publisher, items)
                ui_callback(f'[{publisher}] RSS 수집 실패')
                continue
            # RSS 정보를 먼저 메모리에 모은다. 언론사명은 리더의 고정값을 유지한다.
            temporary_items.extend(dict(item, publisher_name=publisher) for item in items)
        targets, duplicate_count = await duplicate_check.exclude_duplicates(
            connection, temporary_items)
        stats['duplicates'] += duplicate_count
        ui_callback(f'RSS 임시 저장 {len(temporary_items)}건 / 중복 제거 후 {len(targets)}건')
        inserted = dict.fromkeys(latest, 0)
        # 전체 RSS의 중복 제거가 끝난 뒤 URL을 하나씩 수집한다.
        async for item, article in article_reader.iter_articles(session, targets):
            publisher = item['publisher_name']
            if isinstance(article, Exception):
                stats['failed'] += 1
                file_logger.warning('[%s] 기사 URL 수집 실패 %s: %s', publisher, item['url'], article)
                continue
            if article is None:
                stats['skipped'] += 1
                file_logger.info('[%s] 본문/제목/발행시각 누락: %s', publisher, item['url'])
                continue
            # URL의 실제 발행시각도 언론사별 최초 조회 기준 이후인지 확인한다.
            saved_time = latest[publisher]
            if saved_time is not None and article['published_at'] <= saved_time:
                stats['skipped'] += 1
                continue
            article = process_article.process_article(article)
            if article['url'] in seen_urls:
                stats['duplicates'] += 1
                continue
            try:
                result = await db_manager.save_news(connection, **article)
            except Exception:
                stats['failed'] += 1
                file_logger.exception('[%s] 기사 저장 실패: %s', publisher, item['url'])
                continue
            # 저장에 성공한 원본 URL을 기록한다.
            seen_urls.update((item['url'], article['url']))
            inserted[publisher] += int(result.created)
            stats['saved'] += int(result.created)
            stats['duplicates'] += int(not result.created)
        for publisher, count in inserted.items():
            ui_callback(f'[{publisher}] 기사 {count}건 저장 완료')
            file_logger.info('[%s] 기사 %s건 저장', publisher, count)
    ui_callback('모든 언론사 뉴스 수집 완료.')
    return stats


