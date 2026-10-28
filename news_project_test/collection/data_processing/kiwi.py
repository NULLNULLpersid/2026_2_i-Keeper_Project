"""뉴스 본문을 Kiwi로 전처리해 TF-IDF 입력 문자열로 변환한다.

배치 위치: collection/crawler/data_processing/kiwi.py
설치: python -m pip install kiwipiepy
단독 실행: python kiwi.py --text "정부는 AI 산업을 지원한다."

사용 예:
    processor = KiwiPreprocessor()  # 여러 기사에서 같은 객체를 재사용
    tokens = processor.tokenize(content)  # list[str]
    text = processor.preprocess(content)  # 공백으로 연결한 str
    vector = fitted_vectorizer.transform([text])

tokenize와 preprocess는 각각 분석하므로 같은 기사에 둘 다 필요하다면
tokens = processor.tokenize(content); text = " ".join(tokens)로 사용한다.
모듈 함수 preprocess(content), tokenize(content), analyze(content)도 분석기를 재사용한다.
TF-IDF 키워드 선정에는 analyze(content)의 반환값 전체를 전달한다.

기준:
- NNG, NNP, NNB, VV, VA, MAG, SL, SN 품사만 유지
- 키워드 후보는 NNG, NNP, SL만 유지 (analyze의 keyword_tokens)
- 추출한 토큰에 str.lower() 적용
- 별도의 불용어/길이 필터 없음. 순서와 반복 횟수 유지
- 입력 content는 전체 본문 str이며 원문을 수정하지 않음
- 빈 문자열이나 공백뿐인 입력은 [] 또는 "" 반환

TF-IDF를 새로 학습할 때 이 공백 구분 토큰을 그대로 사용하려면
TfidfVectorizer(tokenizer=str.split, token_pattern=None, lowercase=False)처럼
설정한다. 기본 token_pattern은 한 글자 토큰을 제외할 수 있다.
이미 학습한 변환기는 학습 당시의 설정을 그대로 사용해야 한다.
이 파일은 학습/키워드 선정/분류/DB 저장을 수행하지 않는다.
"""
from __future__ import annotations

import argparse
import json
from threading import Lock


KEEP_TAGS = frozenset({"NNG", "NNP", "NNB", "VV", "VA", "MAG", "SL", "SN"})
KEYWORD_TAGS = frozenset({"NNG", "NNP", "SL"})
LOWERCASE = True


class KiwiPreprocessor:
    """한 번 생성한 Kiwi 객체로 기사별 본문을 분석한다."""

    def __init__(self) -> None:
        from kiwipiepy import Kiwi

        self._kiwi = Kiwi(num_workers=1)
        self._lock = Lock()

    def analyze(self, content: str) -> dict:
        """1회 분석으로 분류용 전체 토큰과 키워드용 후보를 함께 반환한다."""
        if not isinstance(content, str):
            raise TypeError("content는 전체 기사 본문 문자열(str)이어야 합니다.")
        tokens, keyword_tokens = [], []
        if content.strip():
            with self._lock:
                analyzed = self._kiwi.tokenize(content)
            for token in analyzed:
                word = token.form.lower() if LOWERCASE else token.form
                if token.tag in KEEP_TAGS:
                    tokens.append(word)
                if token.tag in KEYWORD_TAGS:
                    keyword_tokens.append(word)
        return {"tokens": tokens, "keyword_tokens": keyword_tokens,
                "tfidf_text": " ".join(tokens)}

    def tokenize(self, content: str) -> list[str]:
        """분류용 8개 품사의 토큰을 반환한다. 순서·중복·한 글자를 유지한다."""
        return self.analyze(content)["tokens"]

    def preprocess(self, content: str) -> str:
        """TF-IDF transform([결과])에 전달할 공백 구분 문자열을 반환한다."""
        return " ".join(self.tokenize(content))


_default_processor: KiwiPreprocessor | None = None
_default_lock = Lock()


def _get_processor() -> KiwiPreprocessor:
    global _default_processor
    with _default_lock:
        if _default_processor is None:
            _default_processor = KiwiPreprocessor()
        return _default_processor


def tokenize(content: str) -> list[str]:
    """공유 Kiwi 분석기로 본문을 토큰 목록으로 변환한다."""
    if not isinstance(content, str):
        raise TypeError("content는 전체 기사 본문 문자열(str)이어야 합니다.")
    if not content.strip():
        return []
    return _get_processor().tokenize(content)


def preprocess(content: str) -> str:
    """공유 Kiwi 분석기로 본문을 TF-IDF 입력 문자열로 변환한다."""
    return " ".join(tokenize(content))


def analyze(content: str) -> dict:
    """전체 토큰과 NNG/NNP/SL 키워드 후보 토큰을 함께 반환한다."""
    if not isinstance(content, str):
        raise TypeError("content는 전체 기사 본문 문자열(str)이어야 합니다.")
    if not content.strip():
        return {"tokens": [], "keyword_tokens": [], "tfidf_text": ""}
    return _get_processor().analyze(content)


def main() -> None:
    parser = argparse.ArgumentParser(description="뉴스 본문의 Kiwi 전처리 확인")
    parser.add_argument("--text", required=True, help="분석할 기사 본문 문자열")
    args = parser.parse_args()
    print(json.dumps(analyze(args.text), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
