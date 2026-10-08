"""실제 OpenAI 임베딩을 녹화한다. **OpenAI 비용이 든다** (문장 약 200개, 매우 적다).

    uv run --env-file .env python scripts/task10/record_embeddings.py

녹화하는 것
    매뉴얼 청크 전부       task10_maintenance/data/index/manual_chunks.jsonl
    EventCard 질의 전부   task10_maintenance/evidence.py 의 card_queries 로 111장에서 만든 것

Notebook 은 녹화본을 쓰지 않는다. 작은 연습 데이터로 혼자 돈다.

녹화는 `data/index/recorded_embeddings/` 에 남고 저장소에 함께 올린다. 그래서
학습자는 키 없이도 진짜 의미 검색 순위를 본다. 매뉴얼이나 질의 규칙을 바꾸면
다시 녹화한다. 이미 녹화된 문장은 다시 부르지 않는다.
"""
from __future__ import annotations

import hashlib
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2] / "task10_maintenance"
sys.path.insert(0, str(ROOT.parent))

from langchain_classic.storage import LocalFileStore  # noqa: E402

from task10_maintenance.evidence import (  # noqa: E402
    NAMESPACE,
    RECORDED_DIMENSIONS,
    RECORDED_MODEL,
    RECORDING,
    card_queries,
    load_cards,
    load_chunks,
    recorded_embeddings,
)

def texts_to_record() -> tuple[list[str], list[str]]:
    chunks = [c.page_content for c in load_chunks()]
    queries: list[str] = []
    for card in load_cards().values():
        for _, text in card_queries(card):
            if text not in queries:
                queries.append(text)
    return chunks, queries


def main() -> None:
    if not os.getenv("OPENAI_API_KEY", "").strip():
        raise SystemExit("OPENAI_API_KEY 가 없습니다. uv run --env-file .env 로 실행하세요.")
    from langchain_openai import OpenAIEmbeddings

    before = len(list(LocalFileStore(str(RECORDING)).yield_keys()))
    live = OpenAIEmbeddings(model=RECORDED_MODEL, dimensions=RECORDED_DIMENSIONS)
    recorder = recorded_embeddings(underlying=live)
    chunks, queries = texts_to_record()
    recorder.embed_documents(chunks)
    for text in queries:
        recorder.embed_query(text)
    # 지금 쓰지 않는 녹화본은 지운다. 매뉴얼을 고치면 옛 청크의 녹화가 남는다.
    # 키는 CacheBackedEmbeddings 가 만드는 것과 같다: 네임스페이스 + sha256(문장).
    store = LocalFileStore(str(RECORDING))
    needed = {NAMESPACE + hashlib.sha256(t.encode("utf-8")).hexdigest() for t in chunks + queries}
    stale = [k for k in store.yield_keys() if k not in needed]
    store.mdelete(stale)
    after = len(list(store.yield_keys()))
    print(f"{NAMESPACE} · 청크 {len(chunks)} · 질의 {len(queries)} · 새로 녹화 {after + len(stale) - before}"
          f" · 지운 옛 녹화 {len(stale)} · 전체 {after}")


if __name__ == "__main__":
    main()
