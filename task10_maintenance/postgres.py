"""Postgres(pgvector) 연결. **선택 기능이다.** 기본은 메모리 FAISS 와 SQLite 다.

    VECTOR_BACKEND=pgvector    매뉴얼 청크 vector 를 pgvector 에서 읽는다
    HISTORY_BACKEND=postgres   정비 이력을 Postgres 표에서 읽는다
    DATABASE_URL               둘이 붙을 곳 (postgresql+psycopg://…)

**앱은 읽기만 한다.** 적재는 운영자가 스크립트로 한 번 한다.

    uv run --env-file .env python scripts/task10/ingest_manuals.py --backend pgvector
    uv run --env-file .env python scripts/task10/load_history.py

이력 연결은 세션을 읽기 전용 트랜잭션으로 연다(`default_transaction_read_only`).
SQLite 의 `mode=ro` 와 같은 역할이다. 쓰기 문장은 DB 가 거부한다.
"""
from __future__ import annotations

import os

from shared.rag.store import database_url

LOAD_COMMANDS = ("uv run --env-file .env python scripts/task10/ingest_manuals.py --backend pgvector",
                 "uv run --env-file .env python scripts/task10/load_history.py")


class PostgresUnavailable(RuntimeError):
    """Postgres 를 쓰도록 설정했는데 붙을 수 없거나 적재가 안 되어 있다. 운영자가 고칠 수 있는 상태다."""


def vector_backend() -> str:
    return os.getenv("VECTOR_BACKEND", "faiss").strip().lower() or "faiss"


def history_backend() -> str:
    return os.getenv("HISTORY_BACKEND", "sqlite").strip().lower() or "sqlite"


def required_url() -> str:
    url = database_url()
    if not url:
        raise PostgresUnavailable(
            "Postgres 를 쓰려면 DATABASE_URL 이 필요합니다. DB 를 먼저 띄우세요: docker compose up -d db")
    return url


def psycopg_url(url: str) -> str:
    """SQLAlchemy 형식(postgresql+psycopg://)을 psycopg 가 읽는 형식으로 바꾼다."""
    return url.replace("postgresql+psycopg://", "postgresql://", 1)


def connect(read_only: bool = True):
    """psycopg 연결. 기본은 읽기 전용 세션이다. 행은 dict 로 돌려준다."""
    import psycopg
    from psycopg.rows import dict_row

    options = "-c default_transaction_read_only=on" if read_only else ""
    try:
        return psycopg.connect(psycopg_url(required_url()), options=options, row_factory=dict_row,
                               connect_timeout=5)
    except psycopg.OperationalError as error:
        raise PostgresUnavailable(
            f"Postgres 에 붙을 수 없습니다: {type(error).__name__}. "
            "DB 가 떠 있는지 확인하세요: docker compose ps db") from error
