"""국민일보 RSS 전용 리더. author=국민일보는 기자 정보로 사용하지 않는다."""
from . import common

PUBLISHER_NAME = "국민일보"
ALIASES = ("국민일보",)

def parse_feed(payload):
    results = []
    for item in common.rss_items(payload):
        url = common.field(item, "link")
        if url:
            results.append(dict(publisher_name=PUBLISHER_NAME, url=url,
                title=common.field(item, "title"),
                author=clean_author(common.field(item, "author", "creator")),
                published_at=common.parse_datetime(common.field(item, "pubDate"))))
    return results

def clean_author(value):
    return common.clean_author(value, PUBLISHER_NAME, ALIASES)

def extract_author(html, metadata=None, content=None):
    return common.extract_url_author(html, metadata, content, PUBLISHER_NAME, ALIASES,
        extra_xpaths=("//*[contains(@class,'author')]", "//*[contains(@class,'writer')]",))