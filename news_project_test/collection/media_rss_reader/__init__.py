"""설정의 언론사명으로 고정 언론사 리더를 선택한다. 미등록 리더는 명시적으로 거부한다."""
from . import boannews, kukminilbo

READERS = {alias: module for module in (boannews, kukminilbo) for alias in module.ALIASES}


def get_reader(publisher_name):
    try:
        return READERS[publisher_name]
    except KeyError:
        raise ValueError(f"{publisher_name!r}의 RSS 리더가 등록되지 않았습니다. "
                         "media_rss_reader에 전용 모듈을 추가하고 READERS에 등록하세요.") from None