"""UI 가 실제로 렌더링되고 API 응답을 화면에 올리는지. HTTP 호출만 바꿔 끼운다."""
from pathlib import Path
from unittest.mock import patch

import pytest
from streamlit.testing.v1 import AppTest

ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "streamlit_app.py"

APPS = {"task10_maintenance": "task10_maintenance.app"}


def _client(project: str):
    import importlib

    from fastapi.testclient import TestClient

    return TestClient(importlib.import_module(APPS[project]).create_app())


def _fixture_call(project, path, payload):
    """HTTP 대신 앱을 직접 부른다. 검증 대상은 UI 렌더링이다."""
    return _client(project).post(path, json=payload).json()


def _fixture_read(project, path, **kwargs):
    return _client(project).get(path).json()


@pytest.fixture
def app(monkeypatch):
    for name in ("VECTOR_BACKEND", "HISTORY_BACKEND", "THREAD_DB", "MCP_MODE"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("APP_MODE", "fixture")
    with patch("app_pages._common.call", side_effect=_fixture_call), \
         patch("app_pages._common.read", side_effect=_fixture_read):
        yield AppTest.from_file(str(APP), default_timeout=60).run()


def test_the_page_stops_for_review_and_then_reports(app):
    assert not app.exception
    assert app.title[0].value == "과제 10 · 설비 이상 대응 지원"

    app.button(key="t10_submit").click().run()

    assert not app.exception
    result = app.session_state["t10_result"]
    assert result["status"] == "awaiting_review", "사람 앞에서 멈추지 않았다"
    assert result["packet"]["evidence"], "근거 없이 검토로 넘겼다"
    assert result["executed_actions"] == []

    app.button(key="t10_decide").click().run()

    assert not app.exception
    assert app.session_state["t10_result"]["status"] == "reported"


def test_the_evaluation_tab_shows_the_system_recall(app):
    app.button(key="t10_evaluate").click().run()
    assert not app.exception
    assert app.session_state["t10_evaluation"]["system"]["system_recall"] == 0.747


def test_the_navigation_lists_exactly_the_task10_page():
    source = APP.read_text(encoding="utf-8")
    assert "app_pages/task10_maintenance.py" in source
    for gone in ("s03_", "s04_", "s05_", "s06_", "w1_", "w2_", "w3_"):
        assert gone not in source, f"이 저장소에 없는 화면이 등록되어 있다: {gone}"


def test_ui_never_imports_a_workflow_implementation():
    """UI 는 HTTP 경계를 넘지 않는다. 구현을 직접 부르면 계층이 무너진다."""
    for path in (ROOT / "app_pages").glob("*.py"):
        source = path.read_text(encoding="utf-8")
        for project in (*APPS, "shared"):
            assert f"from {project}" not in source, f"{path.name} 이 {project} 를 직접 import 한다"
            assert f"import {project}" not in source, f"{path.name} 이 {project} 를 직접 import 한다"
