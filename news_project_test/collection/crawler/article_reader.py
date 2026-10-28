"""3단계: 중복이 아닌 RSS URL에 접근해 본문과 기사 메타데이터를 획득한다."""
from __future__ import annotations

import asyncio
from html.parser import HTMLParser
import aiohttp
import trafilatura
import db as db_manager
from .rss_reader import parse_datetime
from ..media_rss_reader import get_reader
from ..media_rss_reader.common import extract_author_contacts

ARTICLE_TIMEOUT = 30


class _PublishedTimeParser(HTMLParser):
    """기사 작성 시각 메타 태그의 시간과 시간대를 그대로 보존한다."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.values = []

    def handle_starttag(self, tag, attrs):
        if tag.lower() != 'meta':
            return
        attrs = dict(attrs)
        name = (attrs.get('property') or attrs.get('name') or '').lower()
        if name in ('article:published_time', 'og:article:published_time'):
            value = attrs.get('content')
            if value:
                self.values.append(value)

def extract_published_at(html, metadata, rss_item):
    """전체 작성 시각 → 일반 메타데이터 날짜 → RSS 작성 시각 순서로 확인한다."""
    parser = _PublishedTimeParser()
    parser.feed(html)
    for value in parser.values:
        published = parse_datetime(value)
        if published is not None:
            return published
    return parse_datetime(getattr(metadata, 'date', None)) or rss_item.get('published_at')


def parse_article(html, final_url, rss_item):
    """URL 메타데이터를 우선하며 누락된 제목·작성자·시각은 RSS 값으로 보완한다."""
    content = trafilatura.extract(html, url=final_url, include_comments=False,
                                  include_images=False, include_tables=False)
    if not content or not content.strip():
        return None
    metadata = trafilatura.extract_metadata(html, default_url=final_url)
    title = getattr(metadata, 'title', None) or rss_item.get('title')
    reader = get_reader(rss_item['publisher_name'])
    # RSS의 기자명을 유지한다. 언론사명 또는 누락 값이면 이미 요청한 기사 HTML에서 추출한다.
    author = reader.clean_author(rss_item.get('author')) or reader.extract_author(html, metadata, content)
    # URL 리더가 반환한 이름에도 RSS와 동일한 정리 규칙을 적용한다.
    author = reader.clean_author(author)
    contact_parser = getattr(reader, 'extract_author_contacts', extract_author_contacts)
    contacts = contact_parser(html, content)
    if reader.PUBLISHER_NAME == '보안뉴스' and contacts:
        author = reader.clean_author([contact['name'] for contact in contacts])
    emails = list(dict.fromkeys(contact['email'] for contact in contacts if contact.get('email')))
    published = extract_published_at(html, metadata, rss_item)
    if not isinstance(title, str) or not title.strip() or published is None:
        return None
    if isinstance(author, (list, tuple)):
        author = ', '.join(str(part).strip() for part in author)
    if author is not None:
        author = str(author).strip() or None
    if author is not None and len(author) > 100:
        raise ValueError('작성자 정보가 DB의 100자 제한을 초과합니다.')
    source_url = db_manager.validate_url(rss_item['url'])
    return dict(publisher_name=reader.PUBLISHER_NAME, title=title.strip(),
                url=source_url, published_at=published,
                author=author, content=content.strip(),
                author_email=', '.join(emails) or None, author_contacts=contacts)


async def fetch_article(session, rss_item, semaphore):
    async with semaphore:
        async with session.get(rss_item['url'], timeout=aiohttp.ClientTimeout(total=ARTICLE_TIMEOUT)) as response:
            response.raise_for_status()
            html = await response.text(errors='replace')
            final_url = str(response.url)
        return await asyncio.to_thread(parse_article, html, final_url, rss_item)


async def iter_articles(session, rss_items, *, request_interval=1.0):
    """기사 URL을 순차 요청한다. 요청 시작 사이에 최소 1초 간격을 둔다.

    응답·본문 처리·호출자의 DB 저장이 오래 걸리면 다음 요청을 즉시 진행한다.
    오류도 (RSS 항목, 예외)로 반환하되 작업 취소는 그대로 전파한다.
    """
    if request_interval < 1.0:
        raise ValueError('기사 요청 간격은 1초 이상이어야 합니다.')
    loop = asyncio.get_running_loop()
    semaphore = asyncio.Semaphore(1)
    last_started = None
    for item in rss_items:
        if last_started is not None:
            remaining = request_interval - (loop.time() - last_started)
            if remaining > 0:
                await asyncio.sleep(remaining)
        last_started = loop.time()
        try:
            article = await fetch_article(session, item, semaphore)
        except Exception as error:
            article = error
        yield item, article


async def fetch_articles(session, rss_items, *, max_concurrent=1):
    """호환용 목록 API. 기사 URL은 항상 1초 간격으로 하나씩 요청한다."""
    if max_concurrent < 1:
        raise ValueError('동시 기사 요청 수는 1 이상이어야 합니다.')
    return [article async for _, article in iter_articles(session, rss_items)]
