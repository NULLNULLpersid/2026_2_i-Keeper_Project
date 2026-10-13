"""2단계: 원본 URL을 검증하고 today_news의 URL과 일괄 비교한다."""
import db as db_manager

async def exclude_duplicates(connection, items, saved_urls=None):
    """
    본문 다운로드 전에 중복을 제외한다. 반환값은 (후보 목록, 중복 개수).

    DB 조회는 URL들을 한 번에 전달한다. saved_urls는 현재 실행에서 저장에
    성공한 URL 집합이며, 실패한 기사까지 제외하지 않도록 읽기만 한다.
    """
    saved_urls = saved_urls if saved_urls is not None else set()
    unique = {}
    duplicates = 0
    for item in items:
        # 유효하지 않은 URL은 HTTP 본문 요청 후보에서 제외한다.
        try:
            canonical = db_manager.validate_url(item['url'])
        except (ValueError, TypeError, KeyError, AttributeError):
            continue
        if canonical in saved_urls or canonical in unique:
            duplicates += 1
            continue
        unique[canonical] = dict(item)
    if not unique:
        return [], duplicates
    existing = await db_manager.get_existing_urls(connection, list(unique))
    duplicates += sum(url in existing for url in unique)
    return [item for url, item in unique.items() if url not in existing], duplicates
