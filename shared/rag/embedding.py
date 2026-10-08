"""임베딩 모델을 고르는 한 곳.

STEP 03 의 학습 주제 중 하나가 **모델 선택과 차원**이다. 그래서 이름과 차원을
설정으로 두고, 고른 결과를 `embedding_profile` 로 드러낸다. 고를 수 없으면
비교할 수 없다.
"""
from __future__ import annotations

import os

from langchain_core.embeddings import DeterministicFakeEmbedding, Embeddings

from shared.rag.mode import is_live_mode

# 차원이 다르면 같은 표에 넣을 수 없다. 적재와 질의가 같은 값을 써야 한다.
DEFAULT_LIVE_MODEL = "text-embedding-3-small"
DEFAULT_DIMENSIONS = 1536
FIXTURE_DIMENSIONS = 256


class EmbeddingConfigurationError(RuntimeError):
    """임베딩 설정이 잘못됐다. 운영자가 고칠 수 있는 상태다."""


def embedding_profile() -> dict[str, object]:
    """지금 어떤 모델을 몇 차원으로 쓰는지. 진단과 Notebook 이 함께 읽는다."""
    if not is_live_mode():
        return {"mode": "fixture", "model": "deterministic-fake",
                "dimensions": _dimensions(FIXTURE_DIMENSIONS)}
    return {"mode": "live",
            "model": os.getenv("OPENAI_EMBEDDING_MODEL", DEFAULT_LIVE_MODEL).strip(),
            "dimensions": _dimensions(DEFAULT_DIMENSIONS)}


def embedding_model() -> Embeddings:
    """fixture 는 결정적 가짜, live 는 실제 모델. 그 외에는 모두 같다."""
    profile = embedding_profile()
    if profile["mode"] == "fixture":
        # 같은 문장은 언제나 같은 vector 가 된다. 평가 결과가 흔들리지 않는다.
        return DeterministicFakeEmbedding(size=int(profile["dimensions"]))

    from langchain_openai import OpenAIEmbeddings

    key = os.getenv("OPENAI_API_KEY", "").strip()
    if not key:
        raise EmbeddingConfigurationError(
            "live 모드에는 환경 변수 OPENAI_API_KEY 가 필요합니다."
        )
    return OpenAIEmbeddings(api_key=key, model=str(profile["model"]),
                            dimensions=int(profile["dimensions"]))


def _dimensions(default: int) -> int:
    # 두 이름을 모두 받는다. compose.yml 과 .env.example 이 한동안
    # OPENAI_EMBEDDING_DIMENSIONS 를 썼는데 여기서는 EMBEDDING_DIMENSIONS 만
    # 읽었다. 설정해도 아무 일이 일어나지 않아 원인을 찾기 어려운 형태였다.
    raw = (os.getenv("EMBEDDING_DIMENSIONS", "").strip()
           or os.getenv("OPENAI_EMBEDDING_DIMENSIONS", "").strip())
    if not raw:
        return default
    try:
        value = int(raw)
    except ValueError as error:
        raise EmbeddingConfigurationError(
            "EMBEDDING_DIMENSIONS 는 정수여야 합니다."
        ) from error
    if value < 1:
        raise EmbeddingConfigurationError("EMBEDDING_DIMENSIONS 는 양수여야 합니다.")
    return value
