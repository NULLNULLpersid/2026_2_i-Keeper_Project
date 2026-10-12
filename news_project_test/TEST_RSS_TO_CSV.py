"""RSS 정보만 수집해 DB 컬럼 이름에 맞춘 CSV로 내보내는 임시 실행 파일.

config.py와 같은 프로젝트 루트에 놓고 실행합니다.
    python TEST_RSS_TO_CSV.py
    python TEST_RSS_TO_CSV.py --list
    python TEST_RSS_TO_CSV.py --media "국민일보" --output kukmin_rss.csv
    python TEST_RSS_TO_CSV.py --all
    python TEST_RSS_TO_CSV.py --since "2026-10-07T00:00:00+09:00"
    python TEST_RSS_TO_CSV.py --xml sample.xml --publisher "보안뉴스"

기사 URL 요청, 본문 처리, DB 접속, GUI, 라이브러리 자동 설치는 실행하지 않습니다.
기존 언론사 RSS 리더를 직접 불러옵니다. 리더의 lxml 의존성이 필요합니다.
작성 시간은 UTC ISO 8601, author_contacts는 JSON 문자열로 출력합니다.
canonical_url_hash는 BYTEA의 PostgreSQL 표현(\\x + SHA256 hex)입니다.
news_id/publisher_id/category_id/content는 RSS에서 결정할 수 없어 빈칸입니다.
publisher_name/rss_url은 출처 확인을 위한 추가 컬럼이며 뉴스 테이블 컬럼은 아닙니다.
CSV는 RSS 중간 결과이므로 본문 등 필수값을 채우기 전에는 DB 직접 삽입용이 아닙니다.
--since 생략 시 현재 RSS에 있는 모든 기사를 대상으로 합니다. DB 시각을 읽지 않습니다.
같은 실행 내 정규화 URL 중복을 제거하며 DB 기존 기사와 비교하지 않습니다.
"""
from __future__ import annotations

import argparse
import asyncio
import csv
import hashlib
import importlib.util
import json
from pathlib import Path
import runpy
import sys
from urllib.parse import urlsplit, urlunsplit
from urllib.request import Request, urlopen

PROJECT_ROOT = Path(__file__).resolve().parent
CSV_COLUMNS = (
    'news_id', 'publisher_id', 'category_id', 'title', 'url', 'canonical_url',
    'canonical_url_hash', 'published_at', 'author', 'author_contacts', 'content',
    'publisher_name', 'rss_url', 'author_email',
)


def load_readers():
    """수집 총괄 모듈을 import하지 않아 DB·trafilatura 의존성을 피한다."""
    folders = (
        PROJECT_ROOT / 'collection/crawler/media_rss_reader',
        PROJECT_ROOT / 'collection/crawler/media_rss_reader',
        PROJECT_ROOT / 'collection/media_rss_reader',
    )
    folder = next((path for path in folders if (path / '__init__.py').is_file()), None)
    if folder is None:
        raise FileNotFoundError('프로젝트의 언론사별 RSS 리더 폴더를 찾을 수 없습니다.')
    name = '_test_rss_csv_readers'
    spec = importlib.util.spec_from_file_location(
        name, folder / '__init__.py', submodule_search_locations=[str(folder)])
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def normalize_url(url):
    """프로젝트 DB와 동일하게 호스트·기본 포트·fragment만 정규화한다."""
    parsed = urlsplit(url.strip())
    scheme = parsed.scheme.lower()
    if scheme not in ('http', 'https') or not parsed.hostname or parsed.username or parsed.password:
        raise ValueError('인증 정보 없는 HTTP(S) 기사 URL이 필요합니다.')
    host = parsed.hostname.lower()
    host = f'[{host}]' if ':' in host else host.encode('idna').decode('ascii')
    port = parsed.port
    if port and (scheme, port) not in (('http', 80), ('https', 443)):
        host += f':{port}'
    return urlunsplit((scheme, host, parsed.path or '/', parsed.query, ''))


def configured_feeds(config):
    for group, publishers in config['MEDIA_RSS'].items():
        for name, values in publishers.items():
            values = [values] if isinstance(values, str) else values
            if not isinstance(values, (list, tuple)) or not values:
                raise ValueError(f'{name}: RSS 주소 또는 주소 목록이 필요합니다.')
            for url in values:
                if not isinstance(url, str) or not url.strip():
                    raise ValueError(f'{name}: RSS 주소가 올바르지 않습니다.')
                yield dict(group=group, media_name=name, rss=url.strip())


def read_payload(url, timeout):
    # 호출하는 주소는 RSS 피드뿐이며 기사 링크는 요청하지 않는다.
    request = Request(url, headers={'User-Agent': 'Mozilla/5.0 (compatible; NewsCollection/1.0)'})
    with urlopen(request, timeout=timeout) as response:
        return response.read()


async def collect(feeds, readers, *, timeout, since=None, xml_path=None):
    """피드 오류는 개별 기록하고 성공한 피드 결과는 유지한다."""
    semaphore = asyncio.Semaphore(8)

    async def one(feed):
        async with semaphore:
            reader = readers.get_reader(feed['media_name'])
            if xml_path is not None:
                payload = await asyncio.to_thread(xml_path.read_bytes)
            else:
                payload = await asyncio.to_thread(read_payload, feed['rss'], timeout)
            items = await asyncio.to_thread(reader.parse_feed, payload)
            return reader.PUBLISHER_NAME, items

    results = await asyncio.gather(*(one(feed) for feed in feeds), return_exceptions=True)
    rows, seen = [], set()
    failed = duplicates = skipped = 0
    for feed, result in zip(feeds, results):
        if isinstance(result, Exception):
            failed += 1
            print(f"RSS 실패 [{feed['media_name']}] {feed['rss']}: {result}", file=sys.stderr)
            continue
        publisher, items = result
        for item in items:
            published = item.get('published_at')
            if since is not None and (published is None or published <= since):
                skipped += 1
                continue
            try:
                canonical = normalize_url(item['url'])
            except (ValueError, TypeError, KeyError, AttributeError):
                skipped += 1
                continue
            if canonical in seen:
                duplicates += 1
                continue
            seen.add(canonical)
            row = dict.fromkeys(CSV_COLUMNS, '')
            row.update(title=item.get('title') or '', url=item['url'],
                       canonical_url=canonical,
                       canonical_url_hash='\\x' + hashlib.sha256(canonical.encode('utf-8')).hexdigest(),
                       published_at=published.isoformat() if published is not None else '',
                       author=item.get('author') or '', author_contacts=json.dumps([], ensure_ascii=False),
                       publisher_name=publisher, rss_url=feed['rss'])
            rows.append(row)
        print(f'[{publisher}] RSS 항목 {len(items)}건', flush=True)
    return rows, dict(failed=failed, duplicates=duplicates, skipped=skipped)


def write_csv(path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    # UTF-8 BOM으로 Windows Excel에서 한국어가 깨지지 않도록 한다.
    with path.open('w', encoding='utf-8-sig', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=CSV_COLUMNS)
        writer.writeheader()
        writer.writerows(rows)


def main(argv=None):
    parser = argparse.ArgumentParser(description='RSS 정보만 수집해 CSV로 저장합니다.')
    choice = parser.add_mutually_exclusive_group()
    choice.add_argument('--all', action='store_true', help='설정된 모든 RSS 선택')
    choice.add_argument('--media', nargs='+', help='config.py의 언론사 이름 지정')
    parser.add_argument('--list', action='store_true', help='설정된 RSS 목록만 출력')
    parser.add_argument('--output', type=Path, default=PROJECT_ROOT / 'rss_news.csv')
    parser.add_argument('--since', help='이 작성 시각 이후만 출력. ISO 8601, 시간대 생략 시 한국 시간')
    parser.add_argument('--timeout', type=float, default=20, help='RSS 요청 제한 시간(초)')
    parser.add_argument('--xml', type=Path, help='서버 요청 없이 로컬 RSS XML 테스트')
    parser.add_argument('--publisher', help='--xml 파일을 파싱할 언론사 리더 이름')
    args = parser.parse_args(argv)
    if args.timeout <= 0:
        parser.error('--timeout은 0보다 커야 합니다.')
    if bool(args.xml) != bool(args.publisher):
        parser.error('--xml과 --publisher를 함께 지정하세요.')
    if args.xml and (args.all or args.media or args.list):
        parser.error('--xml은 --all, --media, --list와 함께 사용할 수 없습니다.')
    try:
        if args.xml:
            feeds = [dict(media_name=args.publisher, rss='', group='로컬 XML')]
        else:
            config = runpy.run_path(str(PROJECT_ROOT / 'config.py'))
            feeds = list(configured_feeds(config))
            if args.list:
                for feed in feeds:
                    print(f"[{feed['group']}] {feed['media_name']}: {feed['rss']}")
                return 0
            if not args.all:
                selected = args.media if args.media is not None else config.get('SELECTED_RSS', [])
                selected = [selected] if isinstance(selected, str) else selected
                wanted = set(selected)
                missing = wanted - {feed['media_name'] for feed in feeds}
                if missing:
                    raise ValueError('설정에 없는 언론사: ' + ', '.join(sorted(missing)))
                feeds = [feed for feed in feeds if feed['media_name'] in wanted]
        if not feeds:
            raise ValueError('선택된 RSS가 없습니다. --media 또는 --all을 지정하세요.')
        readers = load_readers()
        since = None
        if args.since:
            common = sys.modules[readers.__name__ + '.common']
            since = common.parse_datetime(args.since)
            if since is None:
                raise ValueError('--since는 작성 날짜와 시간을 포함해야 합니다.')
        rows, stats = asyncio.run(collect(feeds, readers, timeout=args.timeout,
                                         since=since, xml_path=args.xml))
        if stats['failed'] == len(feeds):
            print('모든 RSS가 실패했습니다. CSV를 변경하지 않습니다.', file=sys.stderr)
            return 1
        output = args.output.expanduser().resolve()
        write_csv(output, rows)
        print(f"CSV: {output}\n저장 {len(rows)}건 / 중복 {stats['duplicates']}건 / "
              f"제외 {stats['skipped']}건 / RSS 실패 {stats['failed']}개")
        return 1 if stats['failed'] else 0
    except KeyboardInterrupt:
        print('\nRSS 수집을 중단했습니다.', file=sys.stderr)
        return 130
    except Exception as error:
        print(f'RSS CSV 실행 실패: {error}', file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
