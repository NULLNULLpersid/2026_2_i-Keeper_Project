import os
import tempfile

import config


def get_selected_media(check_vars):
    """현재 체크된 언론사 이름들을 리스트로 추출합니다."""
    selected_media_names = []
    for cat, media_vars in check_vars.items():
        for media_name, var in media_vars.items():
            if var.get():
                selected_media_names.append(media_name)
    return selected_media_names

def toggle_category(check_vars, toggle_states, category):
    """특정 카테고리의 모든 체크박스 상태를 반전(토글)시킵니다."""
    current_state = not toggle_states[category]
    toggle_states[category] = current_state
    for var in check_vars[category].values():
        var.set(current_state)

def update_selected_media_config(selected_list):
    """선택된 언론사 리스트를 프로젝트 루트의 config.py에 저장합니다."""
    try:
        base_dir = os.path.dirname(os.path.abspath(config.__file__))
        config_path = os.path.join(base_dir, "config.py")
            
        with open(config_path, "r", encoding="utf-8") as f:
            lines = f.readlines()
                
        output_lines = []
        found = False
        for line in lines:
            if line.startswith("SELECTED_RSS"):
                output_lines.append(f"SELECTED_RSS = {selected_list!r}\n")
                found = True
            else:
                output_lines.append(line)
        if not found:
            output_lines.append(f"\nSELECTED_RSS = {selected_list!r}\n")
        fd, temp_path = tempfile.mkstemp(dir=base_dir, suffix=".tmp", text=True)
        try:
            with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as f:
                f.writelines(output_lines)
            os.replace(temp_path, config_path)
        finally:
            if os.path.exists(temp_path):
                os.unlink(temp_path)
        config.SELECTED_RSS = list(selected_list)
                    
    except Exception as e:
        print(f"언론사 저장 실패: {e}")


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
