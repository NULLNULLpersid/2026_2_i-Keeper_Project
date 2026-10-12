"""RSS 및 URL 수집 함수의 공통 진입점."""
from pathlib import Path

# crawler.py와 crawler/를 함께 사용하기 위한 하위 모듈 검색 경로.
__path__ = [str(Path(__file__).with_suffix(''))]

from .crawler.RSS_ import get_saved_time, read_rss, read_selected_feeds, USER_AGENT
from .crawler.URL_ import fetch_article, fetch_articles
