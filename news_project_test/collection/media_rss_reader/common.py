"""언론사 리더의 XML·시각·작성자 처리 공통 도구."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
import json
import re
from xml.etree import ElementTree

from lxml import html as html_parser

KST = timezone(timedelta(hours=9))

def parse_datetime(value):
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, str) and len(value.strip()) > 10:
        raw = re.sub(r'\s+', ' ', value.strip())
        try:
            parsed = datetime.fromisoformat(raw.replace('Z', '+00:00'))
        except ValueError:
            try:
                parsed = parsedate_to_datetime(raw)
            except (ValueError, TypeError, OverflowError):
                return None
    else:
        return None
    if parsed.utcoffset() is None:
        parsed = parsed.replace(tzinfo=KST)
    return parsed.astimezone(timezone.utc)


def field(item, *names):
    """namespace와 CDATA 여부와 무관하게 지정한 직접 자식의 값을 읽는다."""
    for name in names:
        for child in item:
            if child.tag.rsplit('}', 1)[-1].lower() == name.lower():
                value = ''.join(child.itertext()).strip()
                if value:
                    return value
    return None

def rss_items(payload):
    root = ElementTree.fromstring(payload)
    return [item for item in root.iter() if item.tag.rsplit('}', 1)[-1] == 'item']

def clean_author(value, publisher, aliases=()):
    """언론사명은 제외하고 작성자 표기의 '기자'와 이메일을 제거한다."""
    if isinstance(value, (list, tuple)):
        names = [clean_author(part, publisher, aliases) for part in value]
        return ', '.join(dict.fromkeys(name for name in names if name)) or None
    if value is None:
        return None
    value = re.sub(r'\s+', ' ', str(value)).strip()
    comparison = re.sub(r'\s+', '', value).casefold()
    names = {re.sub(r'\s+', '', name).casefold() for name in (publisher, *aliases)}
    if not value or comparison in names or comparison.removesuffix('기자') in names:
        return None
    if value.lower().startswith(('http://', 'https://')):
        return None
    value = _EMAIL.sub('', value).replace('기자', '')
    value = re.sub(r'\s+', ' ', value).strip(' ,;<>[]()')
    comparison = re.sub(r'\s+', '', value).casefold()
    return value if value and comparison not in names else None

def _json_authors(value):
    if isinstance(value, dict):
        author = value.get('author')
        for person in author if isinstance(author, list) else [author]:
            if isinstance(person, str):
                yield person
            elif isinstance(person, dict) and person.get('@type') != 'Organization':
                yield person.get('name')
        for key, child in value.items():
            if key != 'author':
                yield from _json_authors(child)
    elif isinstance(value, list):
        for child in value:
            yield from _json_authors(child)

def extract_url_author(html, metadata, content, publisher, aliases=(), extra_xpaths=()):
    """기사 HTML의 작성자 메타정보·JSON-LD·byline에서 기자명을 찾는다."""
    valid = lambda value: clean_author(value, publisher, aliases)
    candidate = valid(getattr(metadata, 'author', None))
    if candidate:
        return candidate
    try:
        tree = html_parser.fromstring(html)
    except (ValueError, TypeError):
        return None
    for expression in (
        '//meta[translate(@name,"ABCDEFGHIJKLMNOPQRSTUVWXYZ","abcdefghijklmnopqrstuvwxyz")="author"]/@content',
        '//meta[@property="article:author"]/@content',
    ):
        for value in tree.xpath(expression):
            candidate = valid(value)
            if candidate:
                return candidate
    for script in tree.xpath('//script[@type="application/ld+json"]/text()'):
        try:
            names = list(_json_authors(json.loads(script)))
        except (ValueError, TypeError):
            continue
        candidate = valid(names)
        if candidate:
            return candidate
    expressions = (*extra_xpaths,
        '//*[contains(concat(" ",normalize-space(@class)," ")," byline ")]',
        '//*[contains(concat(" ",normalize-space(@class)," ")," reporter ")]')
    for expression in expressions:
        for node in tree.xpath(expression):
            value = node.text_content() if hasattr(node, 'text_content') else str(node)
            candidate = _byline(value, valid)
            if candidate:
                return candidate
    # 본문 마지막 부분의 독립된 기자 표기만 확인한다. 문장 속 인물명은 사용하지 않는다.
    for line in reversed((content or '').splitlines()[-10:]):
        candidate = _byline(line, valid)
        if candidate:
            return candidate
    return None

def _byline(value, valid):
    value = re.sub(r'\s+', ' ', value).strip()
    match = re.fullmatch(r'([가-힣]{2,5}(?:\s*(?:,|·|/)?\s*[가-힣]{2,5}){0,4})\s*(기자|특파원)(?:\s+[\w.+-]+@[\w.-]+)?', value)
    return valid(f'{match[1]} {match[2]}') if match else None

_EMAIL = re.compile(r"[A-Za-z0-9.!#$%&'*+/=?^_`{|}~-]+@[A-Za-z0-9](?:[A-Za-z0-9.-]*[A-Za-z0-9])?\.[A-Za-z]{2,}")

def extract_author_contacts(html, content=None):
    """작성자 영역에서 확인되는 이름·이메일 쌍만 반환한다.

    공용 연락처나 본문 속 제보 이메일은 사용하지 않는다. 공동 기자명에
    이메일 하나만 표시되면 누구의 주소인지 추측하지 않는다.
    """
    contacts = []

    def add(name, value):
        if not isinstance(name, str) or not isinstance(value, str):
            return
        name = re.sub(r'\s*(기자|특파원)$', '', name.strip()).strip()
        emails = _EMAIL.findall(value)
        if not name or len(name) > 100 or len(emails) != 1:
            return
        local, domain = emails[0].rsplit('@', 1)
        contact = dict(name=name, email=local + '@' + domain.lower())
        if contact not in contacts:
            contacts.append(contact)

    try:
        tree = html_parser.fromstring(html)
    except (ValueError, TypeError):
        return contacts

    def walk(value):
        if isinstance(value, list):
            for child in value:
                walk(child)
        elif isinstance(value, dict):
            authors = value.get('author', [])
            for author in authors if isinstance(authors, list) else [authors]:
                if isinstance(author, dict):
                    kind = author.get('@type', [])
                    if kind == 'Person' or isinstance(kind, list) and 'Person' in kind:
                        add(author.get('name'), author.get('email'))
            for key, child in value.items():
                if key != 'author':
                    walk(child)

    for script in tree.xpath('//script[@type="application/ld+json"]/text()'):
        try:
            walk(json.loads(script))
        except (ValueError, TypeError):
            continue

    # 독립된 기자 표기만 인정한다. 각 기자가 별도 줄/요소로 표시되면 각각 저장한다.
    lines = list((content or '').splitlines()[-10:])
    for node in tree.xpath('//*[contains(@class,"author") or contains(@class,"writer") '
                           'or contains(@class,"byline") or contains(@class,"reporter") '
                           'or @id="news_util"]'):
        if node.xpath('ancestor::footer'):
            continue
        lines.extend(node.text_content().splitlines())
        for link in node.xpath('.//a[starts-with(@href,"mailto:")]'):
            label = link.text_content().strip()
            address = link.get('href')[7:].split('?')[0]
            if re.fullmatch(r'[가-힣]{2,5}', label):
                add(label, address)
            else:
                lines.append(label + ' ' + address)
    for line in lines:
        line = re.sub(r'\s+', ' ', line).strip()
        match = re.fullmatch(r'([가-힣]{2,5})\s*(?:기자|특파원)\s*[<(]?(' + _EMAIL.pattern + r')[>)]?', line)
        if match:
            add(match[1], match[2])
    return contacts