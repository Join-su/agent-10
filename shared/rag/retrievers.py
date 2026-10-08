"""STEP 04 가 얹는 리트리버 계층.

**전부 라이브러리가 준다.** 여기서 하는 일은 고르고 이어 붙이는 것뿐이다.
BM25 점수식이나 순위 융합식을 직접 쓰지 않는다. 한 번 그렇게 만들어 두었다가
학습자가 실무에서 쓸 이름을 못 배우는 일이 있었다.
"""
from __future__ import annotations

import re
from collections.abc import Callable, Sequence

from langchain_classic.retrievers import (
    EnsembleRetriever,
    MultiQueryRetriever,
)
from langchain_community.retrievers import BM25Retriever
from langchain_core.documents import Document
from langchain_core.language_models import BaseChatModel
from langchain_core.retrievers import BaseRetriever
from langchain_core.vectorstores import VectorStore

DEFAULT_K = 4


class RetrieverConfigurationError(RuntimeError):
    """리트리버 설정이 잘못됐다. 운영자가 고칠 수 있는 상태다."""


WORD_PATTERN = re.compile(r"[0-9A-Za-z가-힣]+")


def korean_bigrams(text: str) -> list[str]:
    """한국어를 BM25 가 쓸 수 있는 토큰으로 바꾼다.

    BM25Retriever 의 기본 토크나이저는 `text.split()` 이다. 영어에는 맞지만
    한국어에는 맞지 않는다. `자기부담금은` 과 `자기부담금` 이 다른 토큰이 되어
    조사 하나에 검색이 어긋난다.

    그래서 단어와 **글자 2개 묶음**을 함께 낸다. `자기부담금은` 은
    `자기·기부·부담·담금·금은` 을 내므로 `자기부담금` 과 네 묶음이 겹친다.
    형태소 분석기를 넣는 것이 정석이지만 무거운 의존성이 붙는다. 여기서는
    **토크나이저가 검색 품질을 좌우한다는 사실**을 보는 것이 목적이다.

    BM25 점수식은 그대로 라이브러리가 계산한다. 바꾸는 것은 입력 토큰뿐이다.
    """
    tokens: list[str] = []
    for word in WORD_PATTERN.findall(text):
        tokens.append(word)
        tokens += [word[i:i + 2] for i in range(len(word) - 1)]
    return tokens


def keyword_retriever(documents: Sequence[Document], *, k: int = DEFAULT_K,
                      preprocess_func: Callable[[str], list[str]] = korean_bigrams,
                      ) -> BaseRetriever:
    """단어가 그대로 겹치는 것을 찾는다.

    약관 조항 번호처럼 **글자가 정확히 맞아야 하는 질의**에 강하다.
    의미 검색은 "제12조"와 "제14조"를 거의 구별하지 못한다.

    가짜 임베딩을 쓰는 fixture 모드에서도 **이 검색기의 순위는 진짜다.**
    BM25 는 임베딩을 쓰지 않기 때문이다.
    """
    if not documents:
        raise RetrieverConfigurationError("BM25 에 넣을 문서가 없습니다.")
    retriever = BM25Retriever.from_documents(list(documents),
                                             preprocess_func=preprocess_func)
    retriever.k = k
    return retriever


def hybrid_retriever(dense: BaseRetriever, sparse: BaseRetriever, *,
                     weights: tuple[float, float] = (0.5, 0.5)) -> BaseRetriever:
    """의미 검색과 단어 검색을 함께 쓴다.

    `EnsembleRetriever` 가 순위를 융합한다(RRF). 식을 직접 쓰지 않는다.
    한쪽만으로는 조항 번호와 상황 설명 중 하나를 놓친다.
    """
    if abs(sum(weights) - 1.0) > 1e-9:
        raise RetrieverConfigurationError(f"가중치 합이 1 이어야 합니다. 받은 값: {weights}")
    return EnsembleRetriever(retrievers=[dense, sparse], weights=list(weights))


def expanded_retriever(base: BaseRetriever, model: BaseChatModel) -> BaseRetriever:
    """질문 하나를 여러 표현으로 바꿔 함께 찾는다.

    사용자가 쓰는 말과 약관이 쓰는 말이 다르다. `MultiQueryRetriever` 가 모델로
    변형을 만들고 결과를 합친다.
    """
    return MultiQueryRetriever.from_llm(retriever=base, llm=model)


def dense_retriever(store: VectorStore, *, k: int = DEFAULT_K) -> BaseRetriever:
    """의미가 가까운 것을 찾는다. 표현이 달라도 뜻이 같으면 찾는다."""
    return store.as_retriever(search_kwargs={"k": k})
