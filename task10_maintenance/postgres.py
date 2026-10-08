"""Postgres 연결. **과제 10 이 쓰는 DB 는 Postgres(pgvector 확장 포함) 하나다.**

    매뉴얼 vector     pgvector 표 (langchain_pg_collection · langchain_pg_embedding)
    정비 이력         maintenance_record · part_usage 표
    검토 대기 건      LangGraph 저장소 표 (shared/graph/checkpoint.py 가 만든다)

`DATABASE_URL` 하나로 셋 다 붙는다. **앱은 업무 데이터를 읽기만 한다.** 적재는 운영자가
스크립트로 한 번 한다.

    docker compose up -d db
    uv run --env-file .env python scripts/task10/ingest_manuals.py
    uv run --env-file .env python scripts/task10/load_history.py

이력 연결은 세션을 읽기 전용 트랜잭션으로 연다(`default_transaction_read_only`).
쓰기 문장은 DB 가 거부한다.
"""
from __future__ import annotations

from shared.rag.store import database_url

LOAD_COMMANDS = ("uv run --env-file .env python scripts/task10/ingest_manuals.py",
                 "uv run --env-file .env python scripts/task10/load_history.py")


class PostgresUnavailable(RuntimeError):
    """Postgres 에 붙을 수 없거나 적재가 안 되어 있다. 운영자가 고칠 수 있는 상태다."""


def required_url() -> str:
    url = database_url()
    if not url:
        raise PostgresUnavailable(
            "DATABASE_URL 이 필요합니다. DB 를 먼저 띄우고 적재하세요: docker compose up -d db")
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
