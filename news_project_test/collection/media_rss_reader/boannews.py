"""보안뉴스 전용 RSS 파서와 기사 작성자·이메일 추출 로직."""
from __future__ import annotations

import re
from urllib.parse import unquote, urlsplit
from lxml import html as lxml_html
from . import common

PUBLISHER_NAME = "보안뉴스"
ALIASES = ("보안뉴스", "보안 뉴스")

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
        extra_xpaths=("//*[@id='news_util']", "//*[contains(@class,'writer')]",))


def _class_xpath(class_name: str) -> str:
    return (
        "contains(concat(' ', normalize-space(@class), ' '), "
        f"' {class_name} ')"
    )


def _clean_name(text: str) -> str:
    text = re.sub(r"\s+", " ", text).strip()
    return re.sub(r"\s*기자\s*$", "", text).strip()


def _email_from_link(link) -> str | None:
    href = (link.get("href") or "").strip()
    if urlsplit(href).scheme.lower() == "mailto":
        value = unquote(urlsplit(href).path).strip()
    else:
        value = link.text_content().strip()
    # 한 작성자 영역의 단일 이메일 주소만 인정한다.
    if re.fullmatch(r"[^\s@,;<>]+@[^\s@,;<>]+\.[^\s@,;<>]+", value):
        return value
    return None


def extract_author_contacts(html: str | bytes, content=None) -> list[dict[str, str | None]]:
    """
    article-writer 영역 안에서만 이름·이메일을 연결한다.

    프로필 이미지, 다른 기사 링크, 페이지 하단의 대표/고충처리 이메일은 제외한다.
    작성자 영역이 없으면 빈 목록을 반환한다.
    여러 이름이 한 영역에 섞여 연결을 확정할 수 없으면 이메일을 연결하지 않는다.
    """
    if not html or not html.strip():
        return []
    if isinstance(html, bytes):
        # 보안뉴스 응답의 명시된 charset은 UTF-8이다.
        html = html.decode("utf-8", errors="replace")
    root = lxml_html.fromstring(html)
    articles = root.xpath(
        f"descendant-or-self::article[{_class_xpath('article-writer')}]"
    )
    contacts: list[dict[str, str | None]] = []
    seen: set[tuple[str, str | None]] = set()
    for article in articles:
        blocks = article.xpath(f".//*[{_class_xpath('article-writer-content')}]")
        for block in blocks or [article]:
            names = list(dict.fromkeys(
                name for node in block.xpath(f".//*[{_class_xpath('article-writer-name')}]")
                if (name := _clean_name(node.text_content()))
            ))
            emails = list(dict.fromkeys(
                email for link in block.xpath(f".//a[{_class_xpath('article-writer-mail')}]")
                if (email := _email_from_link(link))
            ))
            for name in names:
                paired_emails = emails if len(names) == 1 and emails else [None]
                for email in paired_emails:
                    key = (name, email)
                    if key not in seen:
                        seen.add(key)
                        contacts.append({"name": name, "email": email})
    return contacts