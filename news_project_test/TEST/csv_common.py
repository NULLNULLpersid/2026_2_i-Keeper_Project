"""CSV 진단 도구의 공통 URL 변환."""
from urllib.parse import urlsplit, urlunsplit

def normalize_url(url):
    """CSV 참고 열을 위한 정규화. DB 중복 비교에는 사용하지 않는다."""
    parsed = urlsplit(url.strip())
    scheme = parsed.scheme.lower()
    if scheme not in ("http", "https") or not parsed.hostname or parsed.username or parsed.password:
        raise ValueError("인증 정보 없는 HTTP(S) 기사 URL이 필요합니다.")
    host = parsed.hostname.lower()
    host = f"[{host}]" if ":" in host else host.encode("idna").decode("ascii")
    port = parsed.port
    if port and (scheme, port) not in (("http", 80), ("https", 443)):
        host += f":{port}"
    return urlunsplit((scheme, host, parsed.path or "/", parsed.query, ""))

