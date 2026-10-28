"""언론사 선택 저장과 RSS 목록 변환."""
from setting.setting import save_config

def update_selected_media_config(selected_list):
    save_config({"SELECTED_RSS": list(dict.fromkeys(selected_list))})


def iter_rss_feeds(media_rss):
    """문자열 1개 또는 URL 목록을 개별 RSS 요청 정보로 펼친다."""
    for group, publishers in media_rss.items():
        for name, values in publishers.items():
            urls = [values] if isinstance(values, str) else values
            if not isinstance(urls, (list, tuple)) or not urls:
                raise ValueError(f'{name}: RSS URL 또는 비어 있지 않은 URL 목록이 필요합니다.')
            for url in urls:
                if not isinstance(url, str) or not url.strip():
                    raise ValueError(f'{name}: 올바른 RSS URL 문자열이 필요합니다.')
                yield dict(group=group, media_name=name, rss=url.strip())


def build_selected_feeds(media_rss, selected_names):
    selected = set(selected_names)
    return [dict(media_name=feed['media_name'], rss=feed['rss'])
            for feed in iter_rss_feeds(media_rss) if feed['media_name'] in selected]
