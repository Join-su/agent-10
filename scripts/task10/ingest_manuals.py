"""정비 매뉴얼을 청크로 자르고 벡터 저장소에 담는다.

    uv run python scripts/task10/ingest_manuals.py                  # fixture, FAISS
    uv run python scripts/task10/ingest_manuals.py --backend chroma
    uv run --env-file .env python scripts/task10/ingest_manuals.py   # live 임베딩
    uv run --env-file .env python scripts/task10/ingest_manuals.py --backend pgvector   # 앱이 읽을 pgvector 컬렉션

만드는 것
    data/index/manual_chunks.jsonl     청크와 메타데이터 (눈으로 확인하는 용도)
    data/index/<backend>-<md|pdf>-<mode>-<차원>/ 벡터 저장소 (FAISS 파일 또는 Chroma 폴더)
    pgvector 는 DB 에 남는다 (DATABASE_URL 필요). 앱이 VECTOR_BACKEND=pgvector 일 때 읽는 컬렉션이다.
        앱과 **같은 임베딩**(fixture 는 녹화된 실제 임베딩, live 는 OpenAI)으로 적재한다.

자르는 방법
    1. 머리말(#~####)로 먼저 나눈다. 절이 곧 근거의 단위이기 때문이다.
    2. 긴 절만 글자 수(기본 600자, 겹침 80자)로 다시 자른다.
    3. 청크 앞에 머리말 경로를 붙인다. 예: "[정비 매뉴얼 > 4. 고장 유형별 … > 4.2 열 방산 고장 (HDF) > 4.2.3 점검 절차]"
    4. 청크마다 인용 ID 를 붙인다. 예: "MC01-MM 4.2.3". SOP-EA-01 5.3 이 요구하는 형식이다.

임베딩과 저장소는 v2 의 `shared/rag` 를 그대로 쓴다. fixture 모드의 임베딩은
결정적 가짜라 **벡터 검색 순위는 의미가 없다.** 같은 질의를 BM25 로도 돌려 보여
준다. BM25 는 임베딩을 쓰지 않으므로 fixture 에서도 순위가 진짜다.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2] / "task10_maintenance"
sys.path.insert(0, str(ROOT.parent))

from langchain_core.documents import Document  # noqa: E402
from langchain_text_splitters import (  # noqa: E402
    MarkdownHeaderTextSplitter,
    RecursiveCharacterTextSplitter,
)

from shared.rag import embedding_model, embedding_profile, keyword_retriever  # noqa: E402
from shared.rag.store import build_store  # noqa: E402

MD_DIR = ROOT / "data" / "manuals" / "md"
PDF_DIR = ROOT / "data" / "manuals" / "pdf"
INDEX_DIR = ROOT / "data" / "index"
COLLECTION = "task10-manuals"

HEADERS = [("#", "h1"), ("##", "h2"), ("###", "h3"), ("####", "h4")]
SECTION_ID = re.compile(r"^(부록\s*[A-Z]|\d+(?:\.\d+)*)\.?\s")
PART_NO = re.compile(r"PN-[A-Z]{2}-\d{4}")
FAILURE_CODE = re.compile(r"\b(TWF|HDF|PWF|OSF|RNF)\b")

SMOKE_QUERIES = [
    "온도 차가 작고 회전수가 낮을 때 점검 절차",
    "PN-FL-3120 교체",
    "TWF 경고 확률이 낮을 때 어떻게 판단하나",
    "복합 고장이면 escalation 해야 하나",
]


def read_markdown(path: Path) -> tuple[dict, str]:
    """앞머리(YAML)와 본문을 나눈다. 앞머리는 메타데이터가 되고 청크에는 들어가지 않는다."""
    text = path.read_text(encoding="utf-8")
    if not text.startswith("---"):
        raise SystemExit(f"{path.name} 에 앞머리가 없습니다.")
    _, front, body = text.split("---", 2)
    return yaml.safe_load(front), body.strip()


def section_of(meta: dict) -> tuple[str, str]:
    """가장 깊은 머리말에서 절 번호를 찾는다. 없으면 한 단계씩 올라간다."""
    path = [meta[k] for k in ("h1", "h2", "h3", "h4") if k in meta]
    for title in reversed(path):
        found = SECTION_ID.match(title)
        if found:
            return found.group(1).replace(" ", " "), " > ".join(path)
    return "", " > ".join(path)


def chunk_markdown(paths: list[Path], size: int, overlap: int) -> list[Document]:
    by_header = MarkdownHeaderTextSplitter(headers_to_split_on=HEADERS, strip_headers=False)
    by_length = RecursiveCharacterTextSplitter(chunk_size=size, chunk_overlap=overlap)
    chunks: list[Document] = []
    for path in paths:
        front, body = read_markdown(path)
        doc_id = front["doc_id"]
        sections = by_length.split_documents(by_header.split_text(body))
        for n, piece in enumerate(sections):
            section_id, section_path = section_of(piece.metadata)
            # 머리말 경로를 청크 앞에 붙인다. "4.2.3 점검 절차" 청크 본문에는 "열 방산
            # 고장(HDF)" 이라는 말이 없다. 붙이지 않으면 HDF 를 찾는 질의가 이 절을 놓친다.
            # 과제 10 사례 126개 질의에서 BM25 가 놓친 수: 붙이기 전 40 → 붙인 뒤 24.
            text = f"[{section_path}]\n{piece.page_content}"
            # Chroma 메타데이터는 문자열·숫자만 받는다. 목록은 쉼표로 잇는다.
            chunks.append(Document(page_content=text, metadata={
                "chunk_id": f"{doc_id}#{n:03d}",
                "doc_id": doc_id,
                "title": front["title"],
                "revision": str(front["revision"]),
                "doc_type": front["doc_type"],
                "section_id": section_id,
                "section_path": section_path,
                "citation": f"{doc_id} {section_id}".strip(),
                "part_numbers": ",".join(sorted(set(PART_NO.findall(text)))),
                "failure_types": ",".join(sorted(set(FAILURE_CODE.findall(text)))),
                "has_table": "|---" in text,
                "source_format": "md",
                "provenance": front["provenance"],
            }))
    return chunks


def chunk_pdfs(paths: list[Path], size: int, overlap: int) -> list[Document]:
    """PDF 변환본을 읽어 자른다. **머리말 구조가 사라지므로 절 번호를 붙일 수 없다.**

    pypdf 가 있어야 한다. 이 차이(md 는 절 단위 인용 가능, PDF 는 쪽 단위만 가능)가
    PDF 를 정본으로 쓰지 않은 이유다.
    """
    try:
        from langchain_community.document_loaders import PyPDFLoader
    except ImportError as error:  # pragma: no cover - 의존성 안내
        raise SystemExit("PDF 를 읽으려면 pypdf 가 필요합니다: uv add pypdf") from error
    by_length = RecursiveCharacterTextSplitter(chunk_size=size, chunk_overlap=overlap)
    chunks: list[Document] = []
    for path in paths:
        try:
            pages = PyPDFLoader(str(path)).load()
        except ImportError as error:
            raise SystemExit("PDF 를 읽으려면 pypdf 가 필요합니다: uv add pypdf") from error
        for n, piece in enumerate(by_length.split_documents(pages)):
            page = int(piece.metadata.get("page", 0)) + 1
            chunks.append(Document(page_content=piece.page_content, metadata={
                "chunk_id": f"{path.stem}#pdf{n:03d}", "doc_id": path.stem,
                "section_id": "", "section_path": "", "citation": f"{path.stem} p.{page}",
                "part_numbers": ",".join(sorted(set(PART_NO.findall(piece.page_content)))),
                "failure_types": ",".join(sorted(set(FAILURE_CODE.findall(piece.page_content)))),
                "has_table": False, "source_format": "pdf", "provenance": "synthetic_manual",
            }))
    return chunks


def store(chunks: list[Document], backend: str, source_format: str):
    """벡터 저장소에 담는다. FAISS·Chroma 는 폴더에 남기고 pgvector 는 DB 에 남긴다.

    폴더와 컬렉션 이름에 원본 형식(md·pdf)을 넣는다. 한때 넣지 않아 PDF 적재가 md
    저장소를 덮어썼다.
    """
    profile = embedding_profile()
    target = INDEX_DIR / f"{backend}-{source_format}-{profile['mode']}-{profile['dimensions']}"
    collection = f"{COLLECTION}-{source_format}"
    if backend == "chroma":
        import shutil

        from langchain_chroma import Chroma

        shutil.rmtree(target, ignore_errors=True)       # 다시 만들 때 쌓이지 않게
        vectors = Chroma(collection_name=collection, embedding_function=embedding_model(),
                         persist_directory=str(target))
        vectors.add_documents(chunks, ids=[c.metadata["chunk_id"] for c in chunks])
        return vectors, target
    if backend == "pgvector":
        from task10_maintenance.evidence import embeddings as app_embeddings, manual_collection

        name = manual_collection() + ("-pdf" if source_format == "pdf" else "")
        vectors = build_store(chunks, backend="pgvector", embeddings=app_embeddings(), collection=name)
        return vectors, f"pgvector 컬렉션 {name} (DATABASE_URL)"
    vectors = build_store(chunks, backend=backend, collection=collection)
    if backend == "faiss":
        vectors.save_local(str(target))
        return vectors, target
    return vectors, "pgvector (DATABASE_URL)"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--backend", choices=["faiss", "chroma", "pgvector"], default="faiss")
    parser.add_argument("--chunk-size", type=int, default=600)
    parser.add_argument("--overlap", type=int, default=80)
    parser.add_argument("--pdf", action="store_true", help="md 대신 PDF 변환본을 읽는다 (pypdf 필요)")
    args = parser.parse_args()

    if args.pdf:
        chunks = chunk_pdfs(sorted(PDF_DIR.glob("*.pdf")), args.chunk_size, args.overlap)
        out = INDEX_DIR / "manual_chunks_pdf.jsonl"
    else:
        chunks = chunk_markdown(sorted(MD_DIR.glob("*.md")), args.chunk_size, args.overlap)
        out = INDEX_DIR / "manual_chunks.jsonl"

    INDEX_DIR.mkdir(parents=True, exist_ok=True)
    with out.open("w", encoding="utf-8") as f:
        for c in chunks:
            f.write(json.dumps({"text": c.page_content, "metadata": c.metadata},
                               ensure_ascii=False) + "\n")

    per_doc: dict[str, int] = {}
    for c in chunks:
        per_doc[c.metadata["doc_id"]] = per_doc.get(c.metadata["doc_id"], 0) + 1
    print(f"청크 {len(chunks)}개 → {out.relative_to(ROOT)}")
    for doc_id, n in per_doc.items():
        print(f"  {doc_id:12} {n:3}개")
    print(f"  평균 {sum(len(c.page_content) for c in chunks) // len(chunks)}자 · "
          f"표 포함 {sum(c.metadata['has_table'] for c in chunks)}개 · "
          f"절 번호 없음 {sum(not c.metadata['section_id'] for c in chunks)}개")

    vectors, where = store(chunks, args.backend, "pdf" if args.pdf else "md")
    profile = embedding_profile()
    if args.backend == "pgvector":
        # 앱과 같은 임베딩으로 적재했다. fixture 는 녹화본이라 녹화에 없는 확인 질의는 vector 로 못 찾는다.
        print(f"\n저장소: {where} · 앱과 같은 임베딩 · 청크 {len(chunks)}개")
        print("vector 확인은 앱의 카드 질의로 합니다(GET /diagnostics, POST /cases).")
        return
    print(f"\n저장소: {args.backend} · 임베딩 {profile['model']} ({profile['dimensions']}차원) · {where}")

    bm25 = keyword_retriever(chunks, k=3)
    note = "" if profile["mode"] == "live" else "  ← fixture: 가짜 임베딩이라 순위 의미 없음"
    for query in SMOKE_QUERIES:
        print(f"\n질의: {query}")
        print("  BM25  :", [d.metadata["citation"] for d in bm25.invoke(query)])
        print("  vector:", [d.metadata["citation"] for d in vectors.similarity_search(query, k=3)], note)


if __name__ == "__main__":
    main()
