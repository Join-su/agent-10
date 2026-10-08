"""STEP 을 지나며 자라는 RAG 계층.

STEP 03 이 체인과 벡터스토어를 놓고, STEP 04 가 리트리버를 얹는다. 각 STEP 앱은
자기 도메인만 갖고 여기를 조립한다. 단계가 이어진다는 것을 코드로 만드는 자리다.
"""
from shared.rag.chain import answer_chain, format_documents
from shared.rag.embedding import embedding_model, embedding_profile
from shared.rag.llm import chat_model
from shared.rag.mode import is_live_mode
from shared.rag.retrievers import (
    dense_retriever,
    expanded_retriever,
    hybrid_retriever,
    keyword_retriever,
    korean_bigrams,
)
from shared.rag.store import (
    backend_availability,
    build_store,
    database_url,
    store_backends,
)

__all__ = [
    "answer_chain", "format_documents",
    "embedding_model", "embedding_profile",
    "chat_model", "is_live_mode",
    "dense_retriever", "keyword_retriever", "hybrid_retriever",
    "expanded_retriever", "korean_bigrams",
    "build_store", "store_backends", "backend_availability", "database_url",
]
