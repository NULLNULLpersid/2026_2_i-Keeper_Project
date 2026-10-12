"""RSS URL 하나에 GET 요청을 한 번 보내고 응답 전체를 콘솔에 출력한다.

실행: python TEST_RSS_RESPONSE.py
다른 RSS: python TEST_RSS_RESPONSE.py --url https://example.com/rss.xml
필요한 패키지: pip install aiohttp

DB 연결, 기사 URL 요청, RSS 파싱, 재시도는 하지 않는다.
리다이렉트도 따라가지 않으므로 HTTP 요청은 정확히 한 번만 보낸다.
"""

import argparse
import asyncio
import sys

import aiohttp


RSS_URL = "https://www.boannews.com/rss/allArticle.xml"
USER_AGENT = "Mozilla/5.0 (compatible; NewsCollection/1.0)"


async def print_rss_response(url: str) -> int:
    timeout = aiohttp.ClientTimeout(total=20)
    async with aiohttp.ClientSession(
        headers={"User-Agent": USER_AGENT}, timeout=timeout
    ) as session:
        # 요청 바디 없음. 리다이렉트 및 재시도 없이 한 번만 요청한다.
        async with session.get(url, allow_redirects=False) as response:
            body = await response.text(errors="replace")

            print(f"요청 URL: {response.url}")
            print("\n[응답 상태 및 헤더]")
            version = response.version
            print(
                f"HTTP/{version.major}.{version.minor} "
                f"{response.status} {response.reason or ''}"
            )
            # 중복 헤더(예: Set-Cookie)도 각각 출력한다.
            for name, value in response.raw_headers:
                print(f"{name.decode('latin-1')}: {value.decode('latin-1')}")

            print("\n[응답 바디 전체]")
            print(body)
            # 오류 응답도 바디까지 출력한 후 종료 상태만 변경한다.
            return 0 if 200 <= response.status < 300 else 1


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(errors="replace")
    parser = argparse.ArgumentParser(description="RSS 응답을 한 번만 요청해 출력")
    parser.add_argument("--url", default=RSS_URL, help="요청할 RSS URL 하나")
    args = parser.parse_args()
    if not args.url.startswith(("https://", "http://")):
        parser.error("--url에는 http:// 또는 https:// 주소를 입력하세요.")
    try:
        return asyncio.run(print_rss_response(args.url))
    except (aiohttp.ClientError, asyncio.TimeoutError) as exc:
        print(f"RSS 요청 실패: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
