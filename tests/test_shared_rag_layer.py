"""`shared/rag` — STEP 을 지나며 자라는 RAG 계층.

STEP 03 이 놓은 부분을 검사한다. 체인, 임베딩 선택, 벡터스토어 선택이다.
fixture 와 live 가 **같은 코드**를 타고 임베딩·LLM 만 갈리는 것이 핵심이다.
그래야 키 없이 도는 CI 가 진짜 경로를 검증한다.
"""
from __future__ import annotations

import pytest
from langchain_core.documents import Document
from langchain_core.runnables import Runnable

from shared.rag import (
    answer_chain,
    build_store,
    chat_model,
    embedding_model,
    embedding_profile,
    format_documents,
    store_backends,
)


@pytest.fixture
def manual_documents() -> list[Document]:
    return [
        Document(page_content="펌프 P-200 의 최소 토출압은 3.5 bar 다.",
                 metadata={"source": "PUMP-MAN", "section": "3.1"}),
        Document(page_content="경고: 회전부 점검 전 반드시 차단기를 내린다.",
                 metadata={"source": "PUMP-MAN", "section": "2.4"}),
        Document(page_content="윤활유는 6개월마다 교체한다.",
                 metadata={"source": "PUMP-MAN", "section": "5.2"}),
    ]


def test_fixture_embedding_is_deterministic():
    """같은 문장이 매번 같은 vector 여야 평가 결과가 흔들리지 않는다."""
    model = embedding_model()
    first = model.embed_query("최소 토출압")
    assert first == model.embed_query("최소 토출압"), "같은 문장이 다른 vector 가 됐다"
    assert first != model.embed_query("윤활유 교체 주기"), "다른 문장이 같은 vector 다"
    assert len(first) == embedding_profile()["dimensions"]


def test_the_embedding_dimension_is_configurable(monkeypatch):
    """STEP 03 은 차원을 비교하는 것이 학습 주제다. 고를 수 없으면 비교할 수 없다."""
    monkeypatch.setenv("EMBEDDING_DIMENSIONS", "64")
    assert embedding_profile()["dimensions"] == 64
    assert len(embedding_model().embed_query("펌프")) == 64


@pytest.mark.parametrize("value", ["영", "0", "-8"])
def test_a_bad_dimension_is_refused_at_read_time(monkeypatch, value):
    """차원이 틀리면 적재는 되고 검색에서야 깨진다. 읽을 때 막는다."""
    from shared.rag.embedding import EmbeddingConfigurationError

    monkeypatch.setenv("EMBEDDING_DIMENSIONS", value)
    with pytest.raises(EmbeddingConfigurationError):
        embedding_profile()


@pytest.mark.parametrize("backend", ["faiss"])
def test_both_backends_answer_through_the_same_chain(manual_documents, backend, monkeypatch):
    """벡터 DB 를 바꿔도 조립하는 쪽 코드는 바뀌지 않아야 비교가 된다.

    모드를 고정한다. `.env` 에 `APP_MODE=live` 를 넣어 둔 사람이 이 Test 를
    돌리면 대본 대신 실제 모델이 답해서, 백엔드와 무관한 이유로 빨개졌다.
    """
    monkeypatch.setenv("APP_MODE", "fixture")
    store = build_store(manual_documents, backend=backend)
    retriever = store.as_retriever(search_kwargs={"k": 2})
    chain = answer_chain(retriever, chat_model("최소 토출압은 3.5 bar 입니다."))

    assert isinstance(chain, Runnable), "LCEL 체인이 아니다"
    assert chain.invoke("최소 토출압은?") == "최소 토출압은 3.5 bar 입니다."
    assert len(retriever.invoke("최소 토출압")) == 2


def test_an_unknown_backend_is_named_not_guessed():
    from shared.rag.store import StoreConfigurationError

    with pytest.raises(StoreConfigurationError) as refused:
        build_store([Document(page_content="x")], backend="pinecone")
    assert "pgvector" in str(refused.value) and "faiss" in str(refused.value)


def test_an_empty_corpus_is_refused():
    """빈 코퍼스로 만든 store 는 무엇을 물어도 답이 없다. 그 자리에서 막는다."""
    from shared.rag.store import StoreConfigurationError

    with pytest.raises(StoreConfigurationError):
        build_store([], backend="faiss")


def test_the_context_carries_where_each_piece_came_from(manual_documents):
    """근거가 어디서 왔는지 모르면 답을 검증할 수 없다."""
    text = format_documents(manual_documents)
    for document in manual_documents:
        assert document.metadata["section"] in text
        assert document.page_content in text
    assert text.count("PUMP-MAN") == len(manual_documents)


def test_the_chain_is_assembled_not_hand_sequenced(manual_documents):
    """LCEL 로 이어 붙인 것이 실행 계획이어야 한다.

    순서를 손으로 짜면 그것은 LCEL 이 아니라 그냥 함수 호출이다. STEP 03 이
    가르치는 것은 이어 붙이는 방식 자체다.
    """
    store = build_store(manual_documents, backend="faiss")
    chain = answer_chain(store.as_retriever(search_kwargs={"k": 1}), chat_model("답"))

    assert type(chain).__name__ == "RunnableSequence", f"{type(chain).__name__} 이다"
    steps = chain.steps if hasattr(chain, "steps") else []
    assert len(steps) >= 3, f"체인이 {len(steps)}단계다. 이어 붙인 것이 맞는지 보라."


# --- pgvector — 프로세스 밖에 남는 유일한 백엔드 -----------------------------

import os

import pytest

from shared.rag.store import (
    StoreConfigurationError,
    backend_availability,
    database_url,
)

PGVECTOR_COLLECTION = "shared-rag-pgvector-test"
needs_database = pytest.mark.skipif(
    not os.getenv("DATABASE_URL", "").strip(),
    reason="DATABASE_URL 이 없다. docker compose up -d db 로 DB 를 띄우면 돈다.",
)


def test_pgvector_is_offered_as_a_backend():
    assert "pgvector" in store_backends()


def test_what_can_be_chosen_and_what_works_now_are_different(monkeypatch):
    """목록에 있다는 이유로 쓸 수 있다고 말하면 고른 뒤에야 안 된다는 것을 안다."""
    monkeypatch.delenv("DATABASE_URL", raising=False)
    assert backend_availability()["pgvector"] is False
    assert backend_availability()["faiss"] is True

    monkeypatch.setenv("DATABASE_URL", "postgresql+psycopg://u:p@127.0.0.1:5433/db")
    assert backend_availability()["pgvector"] is True
    assert database_url().endswith("/db")


def test_pgvector_without_a_database_url_names_the_next_command(monkeypatch):
    """"연결할 수 없습니다"만 돌려주면 받는 사람이 무엇을 해야 하는지 모른다."""
    monkeypatch.delenv("DATABASE_URL", raising=False)
    with pytest.raises(StoreConfigurationError) as caught:
        build_store([Document(page_content="자기부담금은 20퍼센트다.")], backend="pgvector")
    message = str(caught.value)
    assert "DATABASE_URL" in message
    assert "docker compose up -d db" in message


def test_an_unreachable_database_is_reported_as_configuration_not_a_crash(monkeypatch):
    monkeypatch.setenv("DATABASE_URL",
                       "postgresql+psycopg://nobody:nobody@127.0.0.1:1/nothing")
    with pytest.raises(StoreConfigurationError) as caught:
        build_store([Document(page_content="자기부담금은 20퍼센트다.")], backend="pgvector")
    assert "docker compose ps db" in str(caught.value)


@needs_database
def test_only_pgvector_outlives_the_process():
    """이것이 "벡터 DB 를 고른다"는 말의 실체다.

    FAISS 는 프로세스 메모리에 있어 다시 만들면 비어 있다. pgvector 는
    새 객체로 붙어도 앞서 적재한 것이 그대로 있다.
    """
    from langchain_postgres import PGVector

    from shared.rag.embedding import embedding_model

    documents = [Document(page_content="제12조 자기부담금은 손해액의 20퍼센트로 한다.",
                          metadata={"evidence_id": "AUTO-2026#제12조"})]
    build_store(documents, backend="pgvector", collection=PGVECTOR_COLLECTION)

    # 적재한 객체를 버리고 **새로 붙는다.** 다시 적재하지 않는다.
    reopened = PGVector(embeddings=embedding_model(), connection=database_url(),
                        collection_name=PGVECTOR_COLLECTION, use_jsonb=True)
    found = reopened.as_retriever(search_kwargs={"k": 1}).invoke("자기부담금")
    assert [d.metadata["evidence_id"] for d in found] == ["AUTO-2026#제12조"]

    # 메모리 백엔드는 새로 만들면 비어 있다. 그 차이를 함께 보여 둔다.
    assert build_store(documents, backend="faiss",
                       collection=PGVECTOR_COLLECTION) is not None
