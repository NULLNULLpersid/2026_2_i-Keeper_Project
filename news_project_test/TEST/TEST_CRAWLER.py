"""GUI 없이 뉴스 수집을 한 번 실행하는 테스트 진입점.

이 파일은 프로젝트의 TEST 폴더에 둡니다.

실행 예:
    python TEST/TEST_CRAWLER.py                    # config.SELECTED_RSS 수집
    python TEST/TEST_CRAWLER.py --list             # 설정된 언론사 목록 확인
    python TEST/TEST_CRAWLER.py --media "보안 뉴스" # 특정 언론사 수집
    python TEST/TEST_CRAWLER.py --all               # 모든 설정 RSS 수집
    python TEST/TEST_CRAWLER.py --path "D:/NewsDB"  # 이번 실행의 DB 저장 경로

실제 프로젝트의 DB에 저장합니다. 중단은 Ctrl+C로 요청합니다.
외부 라이브러리를 자동 설치하지 않으며 main.py와 GUI를 실행하지 않습니다.
"""
from __future__ import annotations

import sys
from pathlib import Path
PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


import argparse
import logging
from pathlib import Path
import signal
import sys
import threading



def build_parser():
    parser = argparse.ArgumentParser(description="프로젝트의 뉴스 수집만 실행합니다.")
    choice = parser.add_mutually_exclusive_group()
    choice.add_argument("--all", action="store_true", help="config.py의 모든 RSS 선택")
    choice.add_argument("--media", nargs="+", metavar="언론사", help="언론사 이름 직접 지정")
    parser.add_argument("--list", action="store_true", help="언론사와 RSS 목록만 출력")
    parser.add_argument("--path", help="이번 실행에서 사용할 DB 저장 경로")
    parser.add_argument("--log", default=str(PROJECT_ROOT / "TEST_CRAWLER.log"),
                        help="수집 로그 파일 경로 (기본: TEST_CRAWLER.log)")
    return parser


def select_feeds(config, args):
    """GUI와 같은 MEDIA_RSS[그룹][언론사] 구조를 사용한다."""
    from collection.media_select import iter_rss_feeds
    available = list(iter_rss_feeds(config.MEDIA_RSS))
    if args.list or args.all:
        return available
    selected = args.media if args.media is not None else config.SELECTED_RSS
    if isinstance(selected, str):
        selected = [selected]
    wanted = set(selected)
    missing = wanted - {feed["media_name"] for feed in available}
    if missing:
        raise ValueError("MEDIA_RSS에 없는 언론사: " + ", ".join(sorted(missing)))
    return [feed for feed in available if feed["media_name"] in wanted]


def main(argv=None):
    args = build_parser().parse_args(argv)
    # 직접 실행 또는 import 호출에서도 프로젝트 모듈을 찾도록 루트를 등록한다.
    if str(PROJECT_ROOT) not in sys.path:
        sys.path.insert(0, str(PROJECT_ROOT))
    try:
        from init import reload_config
        config = reload_config()
        feeds = select_feeds(config, args)
        if args.list:
            for feed in feeds:
                print(f"[{feed["group"]}] {feed["media_name"]} : {feed["rss"]}")
            return 0
        if not feeds:
            print("선택된 RSS가 없습니다. --media, --all 또는 config.SELECTED_RSS를 설정하세요.", file=sys.stderr)
            return 2
        storage_path = args.path or getattr(config, "SAVE_PATH", "")
        if not storage_path:
            raise ValueError("config.SAVE_PATH 또는 --path로 DB 저장 경로를 지정하세요.")
        # 이 import는 목록 확인 이후에 수행하며 GUI/초기 라이브러리 설치 모듈을 읽지 않는다.
        from collection.collection import collect_news_cycle
    except ModuleNotFoundError as exc:
        print(f"필요한 모듈을 찾을 수 없습니다: {exc.name}", file=sys.stderr)
        print("프로젝트 루트와 설치 패키지(aiohttp, feedparser, trafilatura, asyncpg, pgvector)를 확인하세요.", file=sys.stderr)
        return 2
    except Exception as exc:
        print(f"설정 확인 실패: {exc}", file=sys.stderr)
        return 2

    logger = logging.getLogger("TEST_CRAWLER")
    logger.setLevel(logging.INFO)
    logger.propagate = False
    try:
        log_path = Path(args.log).expanduser().resolve()
        log_path.parent.mkdir(parents=True, exist_ok=True)
        handler = logging.FileHandler(log_path, encoding="utf-8")
        handler.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(message)s"))
        logger.addHandler(handler)
    except OSError as exc:
        print(f"로그 파일 생성 실패: {exc}", file=sys.stderr)
        return 2

    stop = threading.Event()
    previous_handler = None
    installed_handler = False

    def request_stop(signum, frame):
        if not stop.is_set():
            print("\n수집 중단을 요청했습니다. 작업과 DB 연결을 정리합니다.", flush=True)
            stop.set()

    try:
        # Python의 signal 등록은 메인 스레드에서만 가능하다.
        if threading.current_thread() is threading.main_thread():
            previous_handler = signal.signal(signal.SIGINT, request_stop)
            installed_handler = True
        print("수집 언론사: " + ", ".join(dict.fromkeys(feed["media_name"] for feed in feeds)))
        print(f"로그 파일: {log_path}")
        logger.info("뉴스 수집 테스트 시작: RSS %s개", len(feeds))
        result = collect_news_cycle(
            urls=[dict(media_name=feed["media_name"], rss=feed["rss"]) for feed in feeds],
            path=storage_path, cancel_event=stop,
            ui_callback=lambda message: print(message, flush=True), file_logger=logger,
        )
        if stop.is_set():
            return 130
        if result is None:
            logger.error("수집 결과를 반환받지 못했습니다.")
            return 1
        print("결과: " + ", ".join(f"{name}={count}" for name, count in result.items()))
        logger.info("수집 결과: %s", result)
        return 1 if result.get("failed", 0) else 0
    except KeyboardInterrupt:
        stop.set()
        return 130
    except Exception as exc:
        logger.exception("뉴스 수집 테스트 실행 실패")
        print(f"수집 실행 실패: {exc}\n상세 로그: {log_path}", file=sys.stderr)
        return 1
    finally:
        if installed_handler:
            signal.signal(signal.SIGINT, previous_handler)
        logger.removeHandler(handler)
        handler.close()


if __name__ == "__main__":
    raise SystemExit(main())
