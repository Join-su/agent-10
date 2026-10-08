"""벡터스토어를 고르는 한 곳.

STEP 03 의 학습 주제 중 하나가 **벡터 DB 선택**이다. 셋을 같은 인터페이스로
놓아야 바꿔 보며 비교할 수 있다. 전부 LangChain 의 `VectorStore` 계약을 따르므로
조립하는 쪽 코드는 바뀌지 않는다.

| 백엔드 | 어디에 있나 | 언제 쓰나 |
|---|---|---|
| `chroma` | 프로세스 메모리 | 기본값. 키도 DB 도 없이 돈다 |
| `faiss` | 프로세스 메모리 | 같은 코드가 다른 구현에서도 도는지 확인할 때 |
| `pgvector` | 별도 Postgres | 프로세스가 죽어도 남아야 할 때. 운영 형태다 |

앞의 둘은 프로세스가 끝나면 사라진다. 세 번째만 남는다. **그 차이가
"벡터 DB 를 고른다"는 말의 실체다.**
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
    return ("chroma", "faiss", "pgvector")


def database_url() -> str:
    """pgvector 가 붙을 곳. 없으면 빈 문자열."""
    return os.getenv("DATABASE_URL", "").strip()


def backend_availability() -> dict[str, bool]:
    """**지금** 쓸 수 있는 것. 고를 수 있는 것과 다르다.

    pgvector 는 DB 가 떠 있어야 쓸 수 있다. 목록에 있다는 이유로 쓸 수 있다고
    말하면, 고른 뒤에야 안 된다는 것을 알게 된다.
    """
    return {"chroma": True, "faiss": True, "pgvector": bool(database_url())}


def build_store(documents: Sequence[Document], *, backend: str | None = None,
                embeddings: Embeddings | None = None,
                collection: str = "step03") -> VectorStore:
    """문서를 실어 벡터스토어를 만든다.

    `backend` 를 주지 않으면 환경 변수 `VECTOR_BACKEND` 를 보고, 그것도 없으면
    Chroma 를 쓴다. 두 구현이 같은 계약을 따르므로 부르는 쪽은 무엇이 오는지
    몰라도 된다.
    """
    chosen = (backend or os.getenv("VECTOR_BACKEND", "chroma")).strip().lower()
    if chosen not in store_backends():
        raise StoreConfigurationError(
            f"VECTOR_BACKEND 는 {', '.join(store_backends())} 중 하나여야 합니다. 받은 값: {chosen!r}"
        )
    if not documents:
        raise StoreConfigurationError("적재할 문서가 없습니다.")

    model = embeddings or embedding_model()
    if chosen == "chroma":
        from langchain_chroma import Chroma

        # 메모리에 만든다. 프로세스가 끝나면 사라진다.
        #
        # **같은 이름으로 다시 만들면 이전 것을 지운다.** Chroma 는 기본 client 를
        # 프로세스 안에서 공유하므로, 같은 collection 이름으로 `from_documents` 를
        # 두 번 부르면 문서가 쌓인다(47 → 94 → 141). 전략을 여러 개 만드는
        # 평가에서 실행 순서에 따라 점수가 달라졌고, 원인을 찾기 어려운 형태였다.
        # `build_store` 는 "쌓는다"가 아니라 "만든다"여야 한다.
        store = Chroma(collection_name=collection, embedding_function=model)
        store.reset_collection()
        store.add_documents(list(documents))
        return store

    if chosen == "faiss":
        from langchain_community.vectorstores import FAISS

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
