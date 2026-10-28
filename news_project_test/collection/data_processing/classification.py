"""학습된 LightGBM의 카테고리 확률과 상위 2개 라벨을 계산한다.

입력: 학습 당시 TF-IDF 모델로 만든 shape=(1, 어휘 수) CSR 벡터.
모델: news_project/trained_model/LightGBM.joblib (재학습 없음).
NewsClassifier 객체는 프로그램에서 재사용한다. 모델은 첫 예측 때 한 번 로딩한다.
지원: raw LGBMClassifier, classes/model dict, classes/estimators dict.
마지막 형식은 카테고리별 {constant, model} 이진 분류기의 양성 확률을 사용한다.
이진 분류기 확률들의 합은 1일 필요가 없다. 확률 동점은 카테고리명 오름차순.
숫자 라벨만 있는 모델은 문자열 classes 대응표와 함께 저장해야 한다.
임시 joblib은 코드 구성용이며, 운영 시 학습 당시의 TF-IDF/LightGBM 쌍을 배치한다.
"""
from __future__ import annotations
from pathlib import Path
import joblib
import numpy as np
from scipy.sparse import issparse


def default_model_path() -> Path:
    for parent in Path(__file__).resolve().parents:
        if parent.name == 'collection':
            return parent.parent / 'trained_model' / 'LightGBM.joblib'
    return Path(__file__).resolve().parent / 'trained_model' / 'LightGBM.joblib'


MODEL_PATH = default_model_path()


class NewsClassifier:
    """본문 분석/TF-IDF 학습 없이 전체 벡터로 분류만 수행한다."""

    def __init__(self, model_path: str | Path | None = None):
        self.classifier_path = Path(model_path) if model_path is not None else MODEL_PATH
        self._classifier = None

    def predict(self, vector) -> dict:
        """전체 TF-IDF CSR 벡터 1개를 받아 서로 다른 상위 2개 라벨을 반환한다."""
        if not issparse(vector) or vector.ndim != 2 or vector.shape[0] != 1:
            raise ValueError('shape=(1, 어휘 수)의 전체 TF-IDF 희소 벡터가 필요합니다.')
        vector = vector.tocsr(copy=False)
        if vector.nnz == 0 or not np.any(vector.data > 0):
            raise ValueError('분류에 사용할 학습 어휘가 없습니다.')
        if not np.all(np.isfinite(vector.data)) or np.any(vector.data < 0):
            raise ValueError('TF-IDF 점수는 0 이상의 유한한 값이어야 합니다.')
        if self._classifier is None:
            self._classifier = joblib.load(self.classifier_path)
        artifact = self._classifier

        def probabilities(model):
            size = getattr(model, 'n_features_in_', vector.shape[1])
            if size != vector.shape[1]:
                raise ValueError('LightGBM과 TF-IDF의 특성 수가 다릅니다. 학습 당시 모델 쌍을 사용하세요.')
            return np.asarray(model.predict_proba(vector), dtype=float)

        if isinstance(artifact, dict) and 'estimators' in artifact:
            # 카테고리별 이진 분류기를 담은 첨부 테스트 모델 형식.
            classes = list(artifact['classes'])
            estimators = artifact['estimators']
            if len(estimators) != len(classes):
                raise ValueError('classes와 estimators의 개수가 다릅니다.')
            scores = []
            for estimator in estimators:
                constant = estimator.get('constant')
                if constant is not None:
                    scores.append(float(constant))
                else:
                    model = estimator['model']
                    prob = probabilities(model)
                    labels = list(model.classes_)
                    if prob.shape != (1, len(labels)) or 1 not in labels:
                        raise ValueError('이진 분류기의 양성 확률을 확인할 수 없습니다.')
                    scores.append(float(prob[0, labels.index(1)]))
            scores = np.asarray(scores)
        else:
            # raw LGBMClassifier 또는 classes/model을 담은 dict.
            model = artifact['model'] if isinstance(artifact, dict) else artifact
            classes = list(artifact['classes'] if isinstance(artifact, dict) else model.classes_)
            # dict의 classes는 predict_proba 열 순서와 일치해야 한다.
            model_classes = list(model.classes_)
            if all(isinstance(label, str) for label in model_classes) and model_classes != classes:
                raise ValueError('저장된 classes와 분류기의 확률 열 순서가 다릅니다.')
            prob = probabilities(model)
            if prob.shape != (1, len(classes)):
                raise ValueError('확률 배열과 classes의 크기가 다릅니다.')
            scores = prob[0]
        if (len(classes) < 2 or any(not isinstance(label, str) for label in classes)
                or len(set(classes)) != len(classes)):
            raise ValueError('서로 다른 문자열 카테고리명이 2개 이상 필요합니다. 라벨 대응표를 확인하세요.')
        if not np.all(np.isfinite(scores)) or np.any((scores < 0) | (scores > 1)):
            raise ValueError('분류 확률은 0~1 범위의 유한한 값이어야 합니다.')
        order = sorted(range(len(classes)), key=lambda i: (-scores[i], classes[i]))
        first, second = order[:2]
        return dict(label1=classes[first], label2=classes[second],
                    label1_probability=float(scores[first]),
                    label2_probability=float(scores[second]),
                    category_probabilities=[{'label': classes[i], 'probability': float(scores[i])}
                                            for i in order])

