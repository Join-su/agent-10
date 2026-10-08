"""설정이 빠진 것을 500 으로 떨어뜨리지 않는다.

키가 없다거나 DB 가 안 떠 있다는 것은 운영자가 고칠 수 있는 상태다. v2 에서 한때
endpoint 가 예외를 잡지 않아 원인 없는 500 이 나갔고, 이유는 서버 로그에만 남았다.
다른 환경에서 받아 띄운 사람이 500 만 보고 원인을 찾지 못한 일이 실제로 있었다.

**진단 endpoint 는 끝까지 200 이어야 한다.** 무엇이 잘못됐는지 물어볼 곳까지
막히면 남는 것은 추측뿐이다.
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

CASE = {"event_id": "EVT-2025-0034"}


def _clear_caches() -> None:
    """설정을 바꿔도 캐시에 남은 저장소가 답하면 검사가 무의미하다."""
    from task10_maintenance import app as app_module
    from task10_maintenance.evaluation import evaluate
    from task10_maintenance.evidence import hybrid
    from task10_maintenance.history import _store

    for cached in (hybrid, _store, evaluate):
        cached.cache_clear()
    app_module.reset_graph()


@pytest.fixture(autouse=True)
def clean(monkeypatch):
    for name in ("VECTOR_BACKEND", "HISTORY_BACKEND", "DATABASE_URL", "THREAD_DB", "MCP_MODE"):
        monkeypatch.delenv(name, raising=False)
    _clear_caches()
    yield
    _clear_caches()


def _client() -> TestClient:
    from task10_maintenance.app import create_app

    return TestClient(create_app(), raise_server_exceptions=False)


@pytest.fixture
def live_without_a_key(monkeypatch):
    """live 로 켜 두고 키를 빼앗는다. 새 환경에 .env 가 없는 상태다."""
    monkeypatch.setenv("APP_MODE", "live")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)


def test_a_missing_key_answers_503_with_a_reason(live_without_a_key):
    response = _client().post("/cases", json=CASE)
    assert response.status_code == 503, f"{response.status_code} 로 답했다"
    body = response.json()
    assert body["code"] == "case_unavailable"
    assert "OPENAI_API_KEY" in body["message"], f"무엇이 빠졌는지 말하지 않는다: {body['message']}"


def test_diagnostics_still_answers_200_so_it_can_be_used_to_diagnose(live_without_a_key):
    response = _client().get("/diagnostics")
    assert response.status_code == 200
    assert response.json()["mode"] == "live"


@pytest.mark.parametrize("setting", [{"VECTOR_BACKEND": "pgvector"}, {"HISTORY_BACKEND": "postgres"}])
def test_postgres_without_a_database_url_answers_503_and_names_the_command(monkeypatch, setting):
    monkeypatch.setenv("APP_MODE", "fixture")
    for name, value in setting.items():
        monkeypatch.setenv(name, value)

    response = _client().post("/cases", json=CASE)

    assert response.status_code == 503, f"{response.status_code} 로 답했다"
    message = response.json()["message"]
    assert "DATABASE_URL" in message
    assert "docker compose up -d db" in message, f"다음에 칠 명령을 말하지 않는다: {message}"


@pytest.mark.parametrize("setting", [{"VECTOR_BACKEND": "pgvector"}, {"HISTORY_BACKEND": "postgres"}])
def test_a_database_that_is_not_there_answers_503(monkeypatch, setting):
    """주소는 있는데 DB 가 안 떠 있는 경우도 마찬가지다."""
    monkeypatch.setenv("APP_MODE", "fixture")
    monkeypatch.setenv("DATABASE_URL", "postgresql+psycopg://task10:x@127.0.0.1:5999/nothing_here")
    for name, value in setting.items():
        monkeypatch.setenv(name, value)

    response = _client().post("/cases", json=CASE)

    assert response.status_code == 503, f"{response.status_code} 로 답했다"
    assert response.json()["code"] == "case_unavailable"
    assert "docker compose ps db" in response.json()["message"]


def test_fixture_mode_is_untouched(monkeypatch):
    """설정이 없어도 fixture 는 그대로 답한다. 이것이 기본 경로다(메모리 FAISS·SQLite)."""
    monkeypatch.setenv("APP_MODE", "fixture")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    response = _client().post("/cases", json=CASE)
    assert response.status_code == 200
    assert response.json()["packet"]["evidence"], "근거 없이 검토로 넘겼다"
    diagnostics = _client().get("/diagnostics").json()
    assert (diagnostics["vector_backend"], diagnostics["history_backend"]) == ("faiss", "sqlite")


def test_the_handler_refuses_to_swallow_everything():
    """모든 예외를 503 으로 만들면 진짜 버그가 설정 문제로 위장된다."""
    from fastapi import FastAPI

    from shared.http_errors import register_unavailable

    app = FastAPI()
    with pytest.raises(ValueError):
        register_unavailable(app, code="nothing_given")


def test_a_dead_mcp_server_is_mapped_to_503():
    """MCP 서버를 띄우지 못하는 것도 고칠 수 있는 상태다."""
    from shared.tools import McpToolsUnavailable

    handlers = _client().app.exception_handlers
    assert McpToolsUnavailable in handlers, "McpToolsUnavailable 을 잡지 않는다"
    response = handlers[McpToolsUnavailable](None, McpToolsUnavailable("서버가 없습니다"))
    assert response.status_code == 503
