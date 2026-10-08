"""화면이 서버가 보낸 이유를 버리지 않는지.

서버는 설정이 빠진 것을 500 이 아니라 **503 과 사람이 읽을 메시지**로 돌려준다.
운영자가 고칠 수 있는 상태이기 때문이다. 그런데 화면이 그 본문을 버리고
`HTTP 503` 만 보여 주면 그 장치는 없는 것과 같다.

실제로 그랬다. STEP 06 을 띄우고 화면에서 심사를 시작했더니 `HTTP 503` 만 떴고,
서버가 보낸 "THREAD_DB 경로를 열 수 없습니다 …" 는 아무 데도 나오지 않았다.
"""
from __future__ import annotations

import httpx
import pytest

from app_pages._common import WorkflowApiError, call, explain


def _response(status: int, body: object) -> httpx.Response:
    return httpx.Response(status, json=body, request=httpx.Request("POST", "http://x/y"))


def test_a_shared_http_error_message_reaches_the_screen():
    """`shared.http_errors` 는 본문 최상위에 code 와 message 를 둔다."""
    reason = ("THREAD_DB 경로를 열 수 없습니다: /no-such-root/threads.sqlite (OSError). "
              "쓸 수 있는 경로인지 확인하거나 THREAD_DB 를 비워 메모리 저장소로 두세요.")
    shown = explain(_response(503, {"code": "review_unavailable", "message": reason}))

    assert reason in shown, shown
    assert "503" in shown, "무슨 상태였는지도 함께 보여야 한다"


def test_an_http_exception_detail_reaches_the_screen():
    """`HTTPException(detail={...})` 는 FastAPI 가 detail 아래로 감싼다."""
    shown = explain(_response(409, {"detail": {"code": "not_awaiting_decision",
                                               "message": "지금 사람 결정을 기다리고 있지 않습니다."}}))
    assert "지금 사람 결정을 기다리고 있지 않습니다." in shown, shown


def test_a_plain_detail_string_reaches_the_screen():
    shown = explain(_response(422, {"detail": "입력이 계약과 맞지 않습니다."}))
    assert "입력이 계약과 맞지 않습니다." in shown, shown


def test_a_body_without_a_reason_still_says_what_happened():
    """이유를 못 찾았다고 조용히 넘어가면 화면이 비어 버린다."""
    shown = explain(_response(500, {"something": "else"}))
    assert "500" in shown and "실패" in shown, shown


def test_call_raises_with_the_server_reason(monkeypatch):
    """`explain` 이 옳아도 `call` 이 쓰지 않으면 화면은 여전히 이유를 모른다."""
    reason = "live 모드에는 환경 변수 OPENAI_API_KEY 가 필요합니다."

    def fake_post(url, **kwargs):
        return _response(503, {"code": "rag_unavailable", "message": reason})

    monkeypatch.setattr(httpx, "post", fake_post)
    with pytest.raises(WorkflowApiError) as raised:
        call("task10_maintenance", "/cases", {})
    assert reason in str(raised.value), str(raised.value)
