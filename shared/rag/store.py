"""벡터스토어를 만드는 한 곳.

과제 10 앱은 **Postgres 의 pgvector 하나**를 쓴다. 매뉴얼 vector·정비 이력·검토 대기 건이
모두 같은 Postgres 에 있다. FAISS 는 프로세스 메모리에 만드는 것이라 Test 와 비교용으로만 남겼다.
둘 다 LangChain 의 `VectorStore` 계약을 따르므로 조립하는 쪽 코드는 바뀌지 않는다.

| 백엔드 | 어디에 있나 | 언제 쓰나 |
|---|---|---|
| `pgvector` | Postgres | 앱. 프로세스가 죽어도 남는다. 운영 형태다 |
| `faiss` | 프로세스 메모리 | Test·비교. 프로세스가 끝나면 사라진다 |
"""
from __future__ import annotations

import os
from collections.abc import Sequence

from langchain_core.documents import Document
from langchain_core.embeddings import Embeddings
from langchain_core.vectorstores import VectorStore

from shared.rag.embedding import embedding_model


class StoreConfigurationError(RuntimeError):
    """벡터스토어 설정이 잘못됐다. 운영자가 고칠 수 있는 상태다."""


def store_backends() -> tuple[str, ...]:
    """고를 수 있는 것. Notebook 과 진단이 같은 목록을 읽는다."""
    return ("pgvector", "faiss")


def database_url() -> str:
    """pgvector 가 붙을 곳. 없으면 빈 문자열."""
    return os.getenv("DATABASE_URL", "").strip()


def backend_availability() -> dict[str, bool]:
    """**지금** 쓸 수 있는 것. 고를 수 있는 것과 다르다.

    pgvector 는 DB 가 떠 있어야 쓸 수 있다. 목록에 있다는 이유로 쓸 수 있다고
    말하면, 고른 뒤에야 안 된다는 것을 알게 된다.
    """
    return {"pgvector": bool(database_url()), "faiss": True}


def build_store(documents: Sequence[Document], *, backend: str = "pgvector",
                embeddings: Embeddings | None = None,
                collection: str = "task10-manuals") -> VectorStore:
    """문서를 실어 벡터스토어를 만든다. 기본은 pgvector 다(적재 스크립트가 쓴다).

    두 구현이 같은 계약을 따르므로 부르는 쪽은 무엇이 오는지 몰라도 된다.
    """
    chosen = backend.strip().lower()
    if chosen not in store_backends():
        raise StoreConfigurationError(
            f"backend 는 {', '.join(store_backends())} 중 하나여야 합니다. 받은 값: {chosen!r}"
        )
    if not documents:
        raise StoreConfigurationError("적재할 문서가 없습니다.")

    model = embeddings or embedding_model()
    if chosen == "faiss":
        from langchain_community.vectorstores import FAISS

        # 메모리에 만든다. 프로세스가 끝나면 사라진다.
        return FAISS.from_documents(list(documents), model)

    return _pgvector_store(documents, model, collection)


def _pgvector_store(documents: Sequence[Document], model: Embeddings,
                    collection: str) -> VectorStore:
    """별도 Postgres 에 적재한다. 여기만 프로세스 밖에 남는다.

    실패 메시지에 **다음에 칠 명령**을 적는다. "연결할 수 없습니다"만 돌려주면
    받는 사람이 무엇을 해야 하는지 모른다. 한때 그래서 원인을 찾는 데 오래
    걸렸다.
    """
    url = database_url()
    if not url:
        raise StoreConfigurationError(
            "pgvector 를 쓰려면 환경 변수 DATABASE_URL 이 필요합니다. "
            "DB 를 먼저 띄우세요: docker compose up -d db"
        )

    from langchain_postgres import PGVector

    try:
        # pre_delete_collection: 같은 이름으로 다시 적재하면 이전 것을 지운다.
        # 안 그러면 실습 중 같은 문서가 계속 쌓여 검색 결과가 중복된다.
        return PGVector.from_documents(
            list(documents), model, connection=url, collection_name=collection,
            use_jsonb=True, pre_delete_collection=True,
        )
    except Exception as error:
        raise StoreConfigurationError(
            f"pgvector 에 적재하지 못했습니다: {type(error).__name__}. "
            f"DB 가 떠 있는지 확인하세요: docker compose ps db"
        ) from error
