"""전체 Kiwi 토큰으로 TF-IDF 벡터를 한 번 만들고 키워드를 추출한다.

입력: kiwi.analyze(content)의 tokens/keyword_tokens dict.
출력: 전체 CSR vector, keywords(keyword/frequency/score/rank), 통계.
모델: news_project/trained_model/tf-idf.joblib. fit/LightGBM/DB/임베딩 없음.
키워드는 NNG/NNP/SL 후보의 양수 점수를 유지해 최대 30개 선정한다.
전체 토큰의 반복과 순서를 보존하며, 후보만 따로 transform하지 않는다.
TFIDFAnalyzer 객체는 재사용한다. include_vector=False이면 JSON 직렬화 가능.
벡터가 0이면 키워드는 비어 있으며 classification.py에서 분류를 거부한다.
CLI: python tfidf.py --content "기사 본문" --model "모델 경로"
"""
from __future__ import annotations

import argparse
from collections import Counter
import json
from pathlib import Path
from typing import Iterable

import joblib
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.utils.validation import check_is_fitted


def default_model_directory() -> Path:
    here = Path(__file__).resolve()
    for parent in here.parents:
        if parent.name == 'collection':
            return parent.parent / 'trained_model'
    # 프로젝트 루트에 단독으로 배치한 경우에도 같은 모델 폴더를 찾는다.
    return here.parent / 'trained_model'


MODEL_DIRECTORY = default_model_directory()
TFIDF_MODEL_PATH = MODEL_DIRECTORY / 'tf-idf.joblib'


def _tokens(tokens: Iterable[str] | str) -> list[str]:
    if isinstance(tokens, str):
        return tokens.split()
    if isinstance(tokens, (bytes, dict)):
        raise TypeError('tokens는 Kiwi 토큰 문자열 목록 또는 공백 연결 문자열이어야 합니다.')
    try:
        values = list(tokens)
    except TypeError as exc:
        raise TypeError('tokens는 Kiwi 토큰 문자열 목록 또는 공백 연결 문자열이어야 합니다.') from exc
    if any(not isinstance(token, str) or not token or any(ch.isspace() for ch in token)
           for token in values):
        raise ValueError('각 토큰은 공백을 포함하지 않는 비어 있지 않은 문자열이어야 합니다.')
    # 소문자화/중복 제거/추가 품사 필터를 하지 않고 Kiwi 결과를 그대로 사용한다.
    return values


def _find_model(path: str | Path) -> Path:
    path = Path(path).expanduser().resolve()
    if path.is_file():
        return path
    if not path.is_dir():
        raise FileNotFoundError(f'학습된 TF-IDF 모델 경로가 없습니다: {path}')
    candidates = sorted(path.rglob('tf-idf.joblib'))
    direct = path / 'tf-idf.joblib'
    if direct.is_file():
        return direct
    if len(candidates) != 1:
        raise ValueError('tf-idf.joblib 경로를 --model로 명시하세요.')
    return candidates[0]


def _get_vectorizer(artifact, key: str | None) -> TfidfVectorizer:
    if key is not None:
        if isinstance(artifact, TfidfVectorizer):
            raise ValueError('이 파일은 TfidfVectorizer 객체 자체입니다. --key를 생략하세요.')
        if not isinstance(artifact, dict) or key not in artifact:
            raise ValueError(f'모델 dict에 지정한 키가 없습니다: {key}')
        artifact = artifact[key]
    elif isinstance(artifact, dict):
        candidates = [value for value in artifact.values() if isinstance(value, TfidfVectorizer)]
        if not candidates:
            keys = ', '.join(str(k) for k in list(artifact)[:10])
            raise ValueError(f'TF-IDF 변환기가 없는 dict입니다. LightGBM 파일 대신 tf-idf.joblib을 지정하세요. dict 키: {keys}')
        if len(candidates) != 1:
            raise ValueError('모델 dict에 TfidfVectorizer가 여러 개입니다. --key를 지정하세요.')
        artifact = candidates[0]
    if not isinstance(artifact, TfidfVectorizer):
        raise TypeError('학습된 TfidfVectorizer가 필요합니다. 실제 모델 파일과 저장 구조를 확인하세요.')
    check_is_fitted(artifact, attributes=['vocabulary_', 'idf_'])
    return artifact


class TFIDFAnalyzer:
    """전체 TF-IDF 벡터와 후보 키워드를 반환한다."""

    def __init__(self, model_path: str | Path | None = None, *, key: str | None = None):
        self.model_path = _find_model(model_path if model_path is not None else TFIDF_MODEL_PATH)
        self.vectorizer = _get_vectorizer(joblib.load(self.model_path), key)
        self.feature_names = self.vectorizer.get_feature_names_out()

    def transform(self, tokens: Iterable[str] | str):
        """LightGBM에 전달할 전체 TF-IDF 희소 벡터를 반환한다. shape=(1, 학습 어휘 수)."""
        return self.vectorizer.transform([' '.join(_tokens(tokens))]).tocsr()

    def analyze(self, tokens: Iterable[str] | str | dict, *,
                keyword_tokens: Iterable[str] | str | None = None, top_k: int = 30,
                include_vector: bool = True) -> dict:
        if type(top_k) is not int or top_k < 1:
            raise ValueError('top_k는 1 이상의 정수여야 합니다.')
        if isinstance(tokens, dict):
            if keyword_tokens is not None:
                raise ValueError('Kiwi 결과 dict와 keyword_tokens를 중복 지정하지 마세요.')
            keyword_tokens = tokens.get('keyword_tokens')
            tokens = tokens['tokens']
        if keyword_tokens is None:
            raise ValueError('품사 판별에는 Kiwi analyze(content) 결과 또는 keyword_tokens가 필요합니다.')
        values = _tokens(tokens)
        candidates = _tokens(keyword_tokens)
        if Counter(candidates) - Counter(values):
            raise ValueError('키워드 후보는 같은 기사의 전체 토큰에 포함돼야 합니다.')
        allowed = set(candidates)
        text = ' '.join(values)
        counts = Counter(values)
        vector = self.transform(values)
        # 학습 설정의 tokenizer/stop_words/ngram_range를 거친 특성별 빈도.
        # 원래 Kiwi 단어 빈도(frequencies)와 구분한다.
        model_counts = Counter(self.vectorizer.build_analyzer()(text))
        weighted = list(
            ((str(self.feature_names[index]), float(score))
             for index, score in zip(vector.indices, vector.data) if score > 0),
        )
        # 전체 TF-IDF 점수는 그대로 두고 후보 품사를 먼저 걸러낸 뒤 상위 30개를 선정한다.
        eligible = sorted(((word, score) for word, score in weighted if word in allowed),
                          key=lambda value: (-value[1], value[0]))
        result = {
            'token_count': len(values),
            'unique_token_count': len(counts),
            'feature_count': vector.shape[1],
            'positive_feature_count': len(weighted),
            'eligible_keyword_count': len(eligible),
            'frequencies': [
                {'keyword': word, 'frequency': count}
                for word, count in sorted(counts.items(), key=lambda value: (-value[1], value[0]))
            ],
            'keywords': [
                {'keyword': word, 'frequency': model_counts[word], 'score': score, 'rank': rank}
                for rank, (word, score) in enumerate(eligible[:top_k], 1)
            ],
        }
        if include_vector:
            result['vector'] = vector
        return result



def main() -> None:
    parser = argparse.ArgumentParser(description='Kiwi 토큰 빈도 및 학습된 TF-IDF 상위 키워드 확인')
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument('--content', help='Kiwi로 분석할 기사 본문 문자열')
    source.add_argument('--tokens', help='Kiwi의 분류용 공백 연결 토큰 문자열')
    parser.add_argument('--keyword-tokens', help='같은 본문에서 NNG/NNP/SL만 남긴 공백 연결 문자열')
    parser.add_argument('--model', type=Path, default=TFIDF_MODEL_PATH, help='변환기 파일 또는 모델 폴더')
    parser.add_argument('--key', help='변환기 객체가 들어 있는 dict 키')
    parser.add_argument('--top-k', type=int, default=30)
    args = parser.parse_args()
    try:
        if args.content is not None:
            if args.keyword_tokens is not None:
                raise ValueError('--content와 --keyword-tokens는 함께 지정하지 마세요.')
            if __package__:
                from .kiwi import analyze as kiwi_analyze
            else:
                from kiwi import analyze as kiwi_analyze
            tokens = kiwi_analyze(args.content)
        else:
            if args.keyword_tokens is None:
                raise ValueError('--tokens 사용 시 --keyword-tokens도 지정하세요.')
            tokens = {'tokens': args.tokens, 'keyword_tokens': args.keyword_tokens}
        analyzer = TFIDFAnalyzer(args.model, key=args.key)
        print(json.dumps(analyzer.analyze(tokens, top_k=args.top_k, include_vector=False), ensure_ascii=False, indent=2))
    except (OSError, ValueError, TypeError, ImportError, EOFError) as error:
        parser.exit(1, f'TF-IDF 처리 실패: {error}\n')


if __name__ == '__main__':
    main()
