"""저장소 전체에 적용되는 Test 설정. 앱 Test 가 쓰는 Postgres 확인이 여기 있다."""
from __future__ import annotations

import asyncio
import os
import sys
import warnings
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent

# --- Windows 이벤트 루프 ---------------------------------------------------------
# 앱의 검토 대기 건 저장소는 psycopg 비동기 연결이라 Windows 기본 루프(Proactor)를 거부한다.
# 앱은 uvicorn --loop task10_maintenance.loop:selector_loop_factory 로 띄운다. Test 가 만드는 루프
# (TestClient 등)도 같은 루프여야 한다. MCP 서버를 띄우는 Test 는 loop.subprocess_loop 를 직접 쓴다.
if sys.platform == "win32":
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", DeprecationWarning)
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())


# --- Postgres -----------------------------------------------------------------
# 앱의 DB 는 Postgres(pgvector) 하나다. `.env` 에 DATABASE_URL 이 있으면 Test 도 그것을 쓴다.
# 셸에 이미 있으면 셸 값이 이긴다. `.env` 의 다른 값(APP_MODE 등)은 읽지 않는다.
if not os.getenv("DATABASE_URL", "").strip():
    from dotenv import dotenv_values

    _url = (dotenv_values(ROOT / ".env").get("DATABASE_URL") or "").strip() if (ROOT / ".env").is_file() else ""
    if _url:
        os.environ["DATABASE_URL"] = _url

DATABASE_HINT = (
    "앱 Test 는 Postgres 가 필요합니다. 먼저: cp .env.example .env → docker compose up -d db → "
    "uv run --env-file .env python scripts/task10/ingest_manuals.py → "
    "uv run --env-file .env python scripts/task10/load_history.py"
)


@pytest.fixture(scope="session")
def database() -> str:
    """DB 가 떠 있고 적재가 끝났는지 확인한다. 아니면 **건너뛰지 않고** 무엇을 할지 말하며 실패한다.

    DB 가 이 앱의 유일한 저장소라, DB 없이 통과하는 앱 Test 는 아무것도 검사하지 않은 것이다.
    """
    url = os.getenv("DATABASE_URL", "").strip()
    if not url:
        pytest.fail("DATABASE_URL 이 없습니다. " + DATABASE_HINT, pytrace=False)
    import psycopg

    try:
        with psycopg.connect(url.replace("postgresql+psycopg://", "postgresql://", 1), connect_timeout=5) as db:
            db.execute("SELECT count(*) FROM maintenance_record").fetchone()
            db.execute("SELECT count(*) FROM langchain_pg_embedding").fetchone()
    except Exception as error:  # noqa: BLE001 - 어떤 이유든 같은 안내를 한다
        pytest.fail(f"Postgres 에 닿지 않거나 적재 전입니다({type(error).__name__}). " + DATABASE_HINT,
                    pytrace=False)
    return url
