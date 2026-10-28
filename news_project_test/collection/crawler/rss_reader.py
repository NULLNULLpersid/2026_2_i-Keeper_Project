"""언론사별 리더를 호출하여 DB 최신 발행시각 이후의 RSS 기사를 수집한다."""
from __future__ import annotations
import asyncio
import aiohttp
import db as db_manager
from ..media_rss_reader import get_reader
from ..media_rss_reader.common import parse_datetime

RSS_TIMEOUT = 20
USER_AGENT = 'Mozilla/5.0 (compatible; NewsCollection/1.0)'


async def get_saved_time(connection, publisher_name):
    """별칭을 리더의 고정 언론사명으로 바꾼 후 DB에서 최신 발행시각을 조회한다."""
    publisher = get_reader(publisher_name).PUBLISHER_NAME
    return await db_manager.get_last_news_time(connection, publisher)


async def read_rss(session, info, saved_time=None):
    reader = get_reader(info['media_name'])
    async with session.get(info['rss'], timeout=aiohttp.ClientTimeout(total=RSS_TIMEOUT)) as response:
        response.raise_for_status()
        payload = await response.read()
    items = await asyncio.to_thread(reader.parse_feed, payload)
    return [item for item in items if saved_time is None or (
        item['published_at'] is not None and item['published_at'] > saved_time)]


async def read_selected_feeds(session, selected_feeds, saved_times, *, max_concurrent=8):
    if max_concurrent < 1:
        raise ValueError('동시 RSS 요청 수는 1 이상이어야 합니다.')
    semaphore = asyncio.Semaphore(max_concurrent)

    async def read_one(info):
        async with semaphore:
            publisher = get_reader(info['media_name']).PUBLISHER_NAME
            return await read_rss(session, info, saved_times.get(publisher))

    return await asyncio.gather(*(read_one(info) for info in selected_feeds), return_exceptions=True)
