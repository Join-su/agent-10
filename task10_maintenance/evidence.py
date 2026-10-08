"""매뉴얼 근거 찾기 — EventCard 하나로 근거가 될 매뉴얼 절을 찾는다.

    EventCard → 질의 만들기(코드) → 하이브리드 검색(BM25 + 의미) → 절 단위로 모으기 → 인용

질의는 카드의 후보 유형과 근거 신호로 만든다. LLM 에게 질의를 쓰게 하지 않는다.
같은 카드는 언제나 같은 질의가 되어야 결과를 비교할 수 있다.

**임베딩은 세 가지 중 하나다.**

    recorded  실제 OpenAI 임베딩을 녹화해 둔 것. 키 없이도 의미 검색 순위가 진짜다 (기본)
    live      실제 OpenAI 임베딩을 지금 부른다 (APP_MODE=live)

녹화에 없는 문장이 오면 가짜 vector 로 넘어가지 않고 멈춘다. 가짜 순위를 진짜처럼
돌려주는 것보다 멈추는 편이 낫다.
"""
from __future__ import annotations

import json
from contextlib import closing
from functools import lru_cache
from pathlib import Path

from langchain_classic.embeddings import CacheBackedEmbeddings
from langchain_classic.retrievers import EnsembleRetriever
from langchain_classic.storage import LocalFileStore
from langchain_core.documents import Document
from langchain_core.embeddings import Embeddings
from langchain_core.retrievers import BaseRetriever

from shared.rag import dense_retriever, embedding_model, embedding_profile, is_live_mode, keyword_retriever
from shared.rag.store import build_store
from task10_maintenance import postgres
from task10_maintenance.domain import EventCard, EvidenceItem
from task10_maintenance.postgres import PostgresUnavailable, vector_backend

ROOT = Path(__file__).resolve().parent
CHUNKS = ROOT / "data" / "index" / "manual_chunks.jsonl"
EVENTCARDS = ROOT / "data" / "eventcards" / "eventcards.jsonl"
RECORDING = ROOT / "data" / "index" / "recorded_embeddings"
RECORDED_MODEL = "text-embedding-3-small"
RECORDED_DIMENSIONS = 256
NAMESPACE = f"{RECORDED_MODEL}-{RECORDED_DIMENSIONS}-"   # 파일 이름이 되므로 콜론을 쓰지 않는다

PER_QUERY = 3          # 질의 하나에서 가져올 청크 수
WEIGHTS = (0.5, 0.5)   # 의미 검색, BM25

TYPE_NAMES = {
    "TWF": "공구 마모 고장(TWF)",
    "HDF": "열 방산 고장(HDF)",
    "PWF": "전력 고장(PWF)",
    "OSF": "과부하 고장(OSF)",
}
SIGNAL_NAMES = {
    "air_temperature_k": "공기 온도", "process_temperature_k": "공정 온도",
    "rotational_speed_rpm": "회전수", "torque_nm": "토크", "tool_wear_min": "공구 마모 시간",
    "temp_diff_k": "온도 차", "power_w": "기계 출력", "power_w_extreme": "기계 출력",
    "quality_grade": "품질 등급", "load_index": "부하 지수",
}


class NotRecorded(RuntimeError):
    """녹화에 없는 문장이다. live 로 돌리거나 다시 녹화해야 한다."""


class _Unrecorded(Embeddings):
    """녹화에 없는 문장이 오면 멈춘다. CacheBackedEmbeddings 의 '못 찾았을 때' 자리다."""

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        raise NotRecorded(
            f"녹화되지 않은 문장 {len(texts)}개: {texts[0][:40]!r}. "
            "APP_MODE=live 로 실행하거나 scripts/task10/record_embeddings.py 로 다시 녹화하세요.")

    def embed_query(self, text: str) -> list[float]:
        return self.embed_documents([text])[0]


def recorded_embeddings(underlying: Embeddings | None = None) -> Embeddings:
    """녹화된 임베딩. `underlying` 을 주면 없는 것을 그것으로 채워 녹화한다."""
    return CacheBackedEmbeddings.from_bytes_store(
        underlying or _Unrecorded(), LocalFileStore(str(RECORDING)),
        namespace=NAMESPACE, query_embedding_cache=True, key_encoder="sha256")


def embedding_source() -> str:
    return "live" if is_live_mode() else "recorded"


def embeddings() -> Embeddings:
    return embedding_model() if is_live_mode() else recorded_embeddings()


# --- 질의 ----------------------------------------------------------------------

def card_queries(card: EventCard) -> list[tuple[str, str]]:
    """카드 하나에서 (이름, 질의) 목록을 만든다.

    후보 유형마다 판정 기준·점검 절차를 찾는 질의 하나, 그리고 확신도에 따른 대응을
    찾는 질의 하나. 근거 신호 두 개를 덧붙여 같은 유형이라도 무엇이 이상했는지를 싣는다.
    """
    p = card.prediction
    signals = []
    for s in p.top_signals:
        name = SIGNAL_NAMES[s.feature]
        if name not in signals:
            signals.append(name)
    hint = ", ".join(signals[:2])
    queries = [(f"{t} 판정·점검", f"{TYPE_NAMES[t]} 판정 기준과 점검 절차, 조치 — {hint}")
               for t in p.candidates]
    queries.append(("확신도 대응", f"확신도 {p.confidence_level} {card.severity} 이벤트 대응 방법"))
    return queries


# --- 검색 ----------------------------------------------------------------------

def load_chunks(path: Path = CHUNKS) -> list[Document]:
    """ingest_manuals.py 가 만든 청크를 읽는다. 적재 결과를 그대로 쓴다."""
    if not path.exists():
        raise FileNotFoundError(f"청크 파일이 없습니다: {path}. scripts/task10/ingest_manuals.py 를 먼저 실행하세요.")
    chunks = []
    for line in path.read_text(encoding="utf-8").splitlines():
        item = json.loads(line)
        chunks.append(Document(page_content=item["text"], metadata=item["metadata"]))
    return chunks


def manual_collection() -> str:
    """pgvector 컬렉션 이름. 임베딩 출처와 차원마다 따로 둔다. 섞이면 검색이 되지 않는다."""
    dims = RECORDED_DIMENSIONS if embedding_source() == "recorded" else embedding_profile()["dimensions"]
    return f"task10-manuals-{embedding_source()}-{dims}"


def _pgvector_store(vectors: Embeddings, expected: int):
    """적재된 컬렉션을 **읽기만** 한다. 없거나 청크 수가 다르면 적재 명령을 알려 준다."""
    from langchain_postgres import PGVector

    collection = manual_collection()
    try:
        with closing(postgres.connect()) as db:
            row = db.execute(
                "SELECT count(*) AS n FROM langchain_pg_embedding e JOIN langchain_pg_collection c "
                "ON e.collection_id = c.uuid WHERE c.name = %s", (collection,)).fetchone()
    except PostgresUnavailable:
        raise
    except Exception as error:      # 표가 없으면 아직 한 번도 적재하지 않은 DB 다
        raise PostgresUnavailable(
            f"pgvector 에 매뉴얼 청크가 없습니다({type(error).__name__}). 먼저 적재하세요: "
            f"{postgres.LOAD_COMMANDS[0]}") from error
    if row["n"] != expected:
        raise PostgresUnavailable(
            f"pgvector 컬렉션 {collection} 의 청크가 {row['n']}개입니다(기대 {expected}개). "
            f"매뉴얼을 고쳤거나 적재가 안 되었습니다. 다시 적재하세요: {postgres.LOAD_COMMANDS[0]}")
    return PGVector(embeddings=vectors, connection=postgres.required_url(), collection_name=collection,
                    use_jsonb=True, create_extension=False)


@lru_cache(maxsize=4)
def hybrid(source: str, backend: str = "faiss", weights: tuple[float, float] = WEIGHTS) -> BaseRetriever:
    """의미 검색과 BM25 를 EnsembleRetriever 로 합친다. 설정마다 한 번만 만든다.

    의미 검색 저장소는 `VECTOR_BACKEND` 로 고른다. faiss(기본)·chroma 는 켤 때 메모리에
    만들고, pgvector 는 미리 적재한 컬렉션을 읽는다. BM25 는 셋 다 같은 청크 파일로 만든다.
    """
    chunks = load_chunks()
    vectors = embedding_model() if source == "live" else recorded_embeddings()
    if backend == "pgvector":
        store = _pgvector_store(vectors, expected=len(chunks))
    else:
        store = build_store(chunks, backend=backend, embeddings=vectors, collection="task10-manuals")
    return EnsembleRetriever(retrievers=[dense_retriever(store, k=PER_QUERY + 1),
                                         keyword_retriever(chunks, k=PER_QUERY + 1)],
                             weights=list(weights))


def find_evidence(card: EventCard) -> tuple[list[tuple[str, str]], list[EvidenceItem], dict[str, list[str]]]:
    """질의마다 찾고, 같은 절은 한 번만 남긴다. 절이 곧 인용의 단위다."""
    retriever = hybrid(embedding_source(), vector_backend())
    queries = card_queries(card)
    evidence: list[EvidenceItem] = []
    per_query: dict[str, list[str]] = {}
    for label, text in queries:
        found = retriever.invoke(text)[:PER_QUERY]
        per_query[label] = [d.metadata["citation"] for d in found]
        for doc in found:
            citation = doc.metadata["citation"]
            if all(e.evidence_id != citation for e in evidence):
                evidence.append(EvidenceItem(evidence_id=citation, kind="manual",
                                             reason=f"{label} 질의", excerpt=doc.page_content.strip()[:400]))
    return queries, evidence, per_query


@lru_cache(maxsize=1)
def _sections() -> dict[str, str]:
    """인용 ID → 그 절의 본문. 같은 절이 여러 청크면 잇는다."""
    found: dict[str, list[str]] = {}
    for doc in load_chunks():
        found.setdefault(doc.metadata["citation"], []).append(doc.page_content)
    return {k: "\n".join(v) for k, v in found.items()}


def manual_section(citation: str, reason: str) -> EvidenceItem | None:
    """검색하지 않고 절 번호로 바로 가져온다. 판정 기준 절처럼 반드시 있어야 하는 근거에 쓴다."""
    text = _sections().get(citation)
    if text is None:
        return None
    return EvidenceItem(evidence_id=citation, kind="manual", reason=reason, excerpt=text.strip()[:400])


def load_cards(path: Path = EVENTCARDS) -> dict[str, EventCard]:
    cards = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        card = EventCard.model_validate_json(line)
        cards[card.event_id] = card
    return cards
