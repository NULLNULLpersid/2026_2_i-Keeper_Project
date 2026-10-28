"""URL 리스트의 기사 정보를 기존 article_reader.py로 추출해 RSS 테스트와 같은 CSV로 저장.

프로젝트의 TEST 폴더에서 관리합니다.
URL_LIST와 PUBLISHER_NAME을 수정한 뒤: python TEST/TEST_URL_TO_CSV.py
출력 경로 변경: python TEST/TEST_URL_TO_CSV.py --output article_news.csv
기본 출력: test_url_news_날짜_시간.csv (실행마다 새 테스트 CSV 생성)
--output으로 지정한 파일이 이미 존재하면 덮어쓰지 않고 종료합니다.
응답 기록: CSV와 같은 위치의 파일명_responses/ 폴더에 URL별 상태·헤더·본문·오류 저장.
HTTP 오류나 추출 실패도 기록합니다. 원본 파서 import 실패 시에도 응답은 수집합니다.
body.bin은 aiohttp가 Content-Encoding 압축을 해제한 응답 바이트입니다.

DB/RSS 요청/본문 분석 모델은 실행하지 않습니다.
프로젝트의 collection.crawler.article_reader.parse_article 함수와 의존성이 필요합니다.
URL을 순차 요청하며 시작 간격은 최소 1초입니다. 재시도/리다이렉트 요청 없음.
CSV 형식: UTF-8 BOM, 작성 시각 UTC ISO 8601, 연락처 JSON, 해시 BYTEA 표현.
추출은 원본 parse_article을 한 번만 호출하며 본문·제목·작성자 등을 다시 추출하지 않습니다.
본문의 표·사진·댓글 처리와 기자명·이메일 추출 여부는 원본 article_reader.py의 구현을 따릅니다.
같은 HTML과 RSS 보완 정보를 입력했을 때 원본과 같은 추출 결과를 사용합니다.
URL만 입력하면 실제 수집 당시의 RSS 보완 정보가 없어 결과가 달라질 수 있습니다.
PUBLISHER_NAME은 리더 선택에 사용하며 저장할 언론사명은 원본 반환값을 우선합니다.
언론사가 다른 항목은 아래 예시처럼
딕셔너리로 넣고 publisher_name을 지정하세요. 해당 언론사 RSS 리더가 필요합니다.
"""
from __future__ import annotations

import sys
from pathlib import Path
PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


import argparse
import asyncio
import csv
import hashlib
import importlib
import json
import sys
import traceback
from html.parser import HTMLParser
from datetime import datetime, timezone
from pathlib import Path
from TEST.csv_common import normalize_url

import aiohttp


PUBLISHER_NAME = "보안뉴스"
URL_LIST = [
    "https://www.boannews.com/news/articleView.html?idxno=146219",
    # "https://www.boannews.com/news/articleView.html?idxno=다른번호",
    # {"url": "https://다른언론사/기사", "publisher_name": "국민일보",
    #  "title": "RSS 제목", "author": "RSS 기자명",
    #  "published_at": "2026-10-08T12:00:00+09:00", "rss_url": "원본 RSS 주소"},
]
REQUEST_INTERVAL = 1.0
USER_AGENT = "Mozilla/5.0 (compatible; NewsCollection/1.0)"
CSV_COLUMNS = (
    'news_id', 'publisher_id', 'label1_id', 'label2_id', 'title', 'url', 'canonical_url',
    'canonical_url_hash', 'published_at', 'author', 'author_contacts', 'content',
    'publisher_name', 'rss_url', 'author_email',
)



def prepare_items(values, publisher):
    items, seen = [], set()
    for value in values:
        item = dict(value) if isinstance(value, dict) else {'url': value}
        canonical = normalize_url(item['url'])
        if item['url'] in seen:
            print(f"중복 제외: {item['url']}")
            continue
        seen.add(item['url'])
        item.setdefault('publisher_name', publisher)
        item.setdefault('author', None)
        item.setdefault('title', None)
        item.setdefault('published_at', None)
        if not item['publisher_name']:
            raise ValueError('각 URL에 publisher_name을 지정하세요.')
        if isinstance(item['published_at'], str):
            published = datetime.fromisoformat(item['published_at'].replace('Z', '+00:00'))
            if published.tzinfo is None:
                raise ValueError('입력 작성 시각에는 +09:00 등 시간대를 포함하세요.')
            item['published_at'] = published
        items.append(item)
    return items


def make_row(article, item):
    canonical = normalize_url(article.get('canonical_url') or item['url'])
    published = article.get('published_at')
    if not isinstance(published, datetime) or published.tzinfo is None:
        raise ValueError('article_reader.py가 시간대를 포함한 작성 시각을 반환해야 합니다.')
    contacts = article.get('author_contacts') or []
    if isinstance(contacts, str):
        contacts = json.loads(contacts)
    row = dict.fromkeys(CSV_COLUMNS, '')
    row.update(
        title=article.get('title') or '', url=article.get('url') or item['url'], canonical_url=canonical,
        canonical_url_hash='\\x' + hashlib.sha256(canonical.encode('utf-8')).hexdigest(),
        published_at=published.astimezone(timezone.utc).isoformat(),
        author=article.get('author') or '', author_email=article.get('author_email') or '',
        author_contacts=json.dumps(contacts, ensure_ascii=False),
        content=article.get('content') or '',
        publisher_name=article.get('publisher_name') or item['publisher_name'],
        rss_url=item.get('rss_url') or '',
    )
    return row


class ExtractionFailure(ValueError):
    def __init__(self, diagnostics):
        self.diagnostics = diagnostics
        super().__init__('원본 추출 실패. extraction.json에서 본문·제목·작성 시각 진단을 확인하세요.')


def diagnose_extraction(html, final_url, item, article_parser):
    """원본 실패 시에만 재검사한다. 재검사 결과로 원본 반환값을 보완하지 않는다."""
    report = {'rss_title': item.get('title'), 'rss_published_at': item.get('published_at')}
    class MetaReader(HTMLParser):
        def handle_starttag(self, tag, attrs):
            if tag.lower() == 'meta':
                values = dict(attrs)
                if (values.get('property') or values.get('name')) == 'article:published_time':
                    report['html_published_time'] = values.get('content')
    try:
        MetaReader().feed(html)
        original_globals = getattr(article_parser, '__globals__', {})
        extractor = original_globals.get('trafilatura')
        date_parser = original_globals.get('parse_datetime')
        if extractor is not None:
            report['trafilatura_version'] = getattr(extractor, '__version__', None)
            # 확인한 원본 article_reader.py의 본문 추출 옵션과 동일한 진단 호출.
            content = extractor.extract(html, url=final_url, include_comments=False,
                                        include_images=False, include_tables=True)
            metadata = extractor.extract_metadata(html, default_url=final_url)
            report['body_length'] = len(content or '')
            report['metadata_title'] = getattr(metadata, 'title', None)
            report['metadata_date'] = getattr(metadata, 'date', None)
            report['metadata_author'] = getattr(metadata, 'author', None)
            if date_parser is not None:
                report['parsed_metadata_date'] = date_parser(report['metadata_date'])
                report['parsed_html_published_time'] = date_parser(report.get('html_published_time'))
    except Exception:
        report['diagnostic_error'] = traceback.format_exc()
    return report


def parse_html(html, final_url, item, article_parser):
    article = article_parser(html, final_url, item)
    if not article:
        raise ExtractionFailure(diagnose_extraction(html, final_url, item, article_parser))
    # 원본 추출 결과를 변경하지 않고 CSV 표현만 변환한다.
    return make_row(article, item)


def save_json(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, default=str), encoding='utf-8')


async def collect(items, article_parser, timeout, response_dir):
    rows, failed = [], 0
    previous_start = None
    async with aiohttp.ClientSession(
        headers={'User-Agent': USER_AGENT},
        timeout=aiohttp.ClientTimeout(total=timeout),
    ) as session:
        loop = asyncio.get_running_loop()
        for index, item in enumerate(items, 1):
            if previous_start is not None:
                await asyncio.sleep(max(0, REQUEST_INTERVAL - (loop.time() - previous_start)))
            previous_start = loop.time()
            print(f"[{index}/{len(items)}] 요청: {item['url']}", flush=True)
            prefix = response_dir / f'{index:04d}'
            record_path = prefix.with_suffix('.response.json')
            record = {
                'requested_at': datetime.now().astimezone().isoformat(),
                'input': item, 'stage': 'request', 'result': 'pending',
            }
            save_json(record_path, record)
            try:
                # 동시에 요청하는 URL은 하나. 자동 리다이렉트/재시도 없음.
                async with session.get(item['url'], allow_redirects=False) as response:
                    record.update(
                        stage='read_response', final_url=str(response.url),
                        status=response.status, reason=response.reason,
                        http_version=f'{response.version.major}.{response.version.minor}',
                        response_headers=[
                            [name.decode('latin-1'), value.decode('latin-1')]
                            for name, value in response.raw_headers
                        ],
                        request_headers=list(response.request_info.headers.items()),
                        charset=response.charset, body_complete=False, received_bytes=0,
                    )
                    save_json(record_path, record)
                    # HTTP状態判定・記事解析より先に応答を保存する。
                    # 読み取りが途中で失敗した場合も受信済みバイトを残す。
                    body_path = prefix.with_suffix('.body.bin')
                    received = 0
                    with body_path.open('wb') as stream:
                        async for chunk in response.content.iter_chunked(65536):
                            stream.write(chunk)
                            received += len(chunk)
                            record['received_bytes'] = received
                    record['body_complete'] = True
                    record['stage'] = 'decode_response'
                    raw_body = body_path.read_bytes()
                    html = raw_body.decode(response.charset or 'utf-8', errors='replace')
                    prefix.with_suffix('.html').write_text(html, encoding='utf-8')
                    record['stage'] = 'http_status'
                    if not 200 <= response.status < 300:
                        raise ValueError(f'HTTP {response.status}; Location={response.headers.get("Location", "")}')
                    final_url = str(response.url)
                record['stage'] = 'parse_article'
                if article_parser is None:
                    raise RuntimeError('원본 article_reader.py를 불러오지 못했습니다. run.json을 확인하세요.')
                row = await asyncio.to_thread(parse_html, html, final_url, item, article_parser)
                rows.append(row)
                record.update(result='success', stage='complete', title=row['title'])
                print(f"  수집 성공: {row['title']}", flush=True)
            except Exception as error:
                failed += 1
                record.update(result='failed', error_type=type(error).__name__, error=str(error))
                if isinstance(error, ExtractionFailure):
                    save_json(prefix.with_suffix('.extraction.json'), error.diagnostics)
                prefix.with_suffix('.error.txt').write_text(traceback.format_exc(), encoding='utf-8')
                print(f"  수집 실패: {type(error).__name__}: {error}", file=sys.stderr)
            finally:
                record['finished_at'] = datetime.now().astimezone().isoformat()
                save_json(record_path, record)
    return rows, failed


def write_csv(path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    # 새 테스트 파일만 생성한다. 기존 파일은 덮어쓰지 않는다.
    with path.open('x', encoding='utf-8-sig', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=CSV_COLUMNS)
        writer.writeheader()
        writer.writerows(rows)


def main(argv=None):
    parser = argparse.ArgumentParser(description='URL 리스트의 기사 정보를 순차 수집해 CSV 저장')
    parser.add_argument('--output', type=Path, help='새 테스트 CSV 경로 (기존 파일 사용 불가)')
    parser.add_argument('--publisher', default=PUBLISHER_NAME, help='문자열 URL의 고정 언론사명')
    parser.add_argument('--timeout', type=float, default=30, help='요청 제한 시간(초)')
    args = parser.parse_args(argv)
    if args.timeout <= 0:
        parser.error('--timeout은 0보다 커야 합니다.')
    try:
        output = (
            args.output if args.output is not None else
            PROJECT_ROOT / f"test_url_news_{datetime.now().astimezone():%Y%m%d_%H%M%S_%f}.csv"
        ).expanduser().resolve()
        if output.exists():
            raise FileExistsError(f'CSV 파일이 이미 존재합니다. 다른 이름을 지정하세요: {output}')
        items = prepare_items(URL_LIST, args.publisher)
        if not items:
            raise ValueError('URL_LIST에 기사 URL을 넣으세요.')
        response_dir = output.with_name(output.stem + '_responses')
        response_dir.mkdir(parents=True, exist_ok=False)
        print(f'응답·오류 저장 폴더: {response_dir}', flush=True)
        run_record = {'python': sys.version, 'inputs': items, 'csv_path': str(output),
                      'timeout': args.timeout, 'request_interval': REQUEST_INTERVAL}
        article_parser = None
        try:
            module = importlib.import_module('collection.crawler.article_reader')
            article_parser = module.parse_article
            run_record['parser_file'] = str(module.__file__)
        except Exception:
            run_record['parser_import_error'] = traceback.format_exc()
            print('원본 추출 모듈을 불러오지 못했습니다. 응답만 저장합니다.', file=sys.stderr)
        save_json(response_dir / 'run.json', run_record)
        rows, failed = asyncio.run(collect(items, article_parser, args.timeout, response_dir))
        save_json(response_dir / 'summary.json', {'requested_urls': len(items),
                                                'saved_articles': len(rows), 'failed': failed})
        if not rows:
            print('저장할 기사가 없습니다. 기존 CSV를 변경하지 않습니다.', file=sys.stderr)
            return 1
        write_csv(output, rows)
        print(f'CSV: {output}\n저장 {len(rows)}건 / 실패 {failed}건')
        return 1 if failed else 0
    except KeyboardInterrupt:
        print('\n수집을 중단했습니다.', file=sys.stderr)
        return 130
    except Exception as error:
        print(f'URL CSV 실행 실패: {type(error).__name__}: {error}', file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
