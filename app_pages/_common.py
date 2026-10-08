"""UI가 API를 부르는 유일한 경로. 워크플로 구현을 직접 import하지 않는다."""
from __future__ import annotations

import os
from typing import Any

import httpx
import streamlit as st

API_TARGETS = {
    "task10_maintenance": ("TASK10_API_URL", "http://127.0.0.1:8035"),
}


class WorkflowApiError(RuntimeError):
    """UI가 API 결과를 얻지 못했을 때."""


def api_base(project: str) -> str:
    key, default = API_TARGETS[project]
    return os.getenv(key, default)


def explain(response: httpx.Response) -> str:
    """서버가 보낸 이유를 그대로 화면에 올린다.

    **서버는 503 에 원인을 담아 보낸다.** 설정이 빠진 것은 운영자가 고칠 수 있는
    상태이므로 무엇이 빠졌는지 말해 주려고 만든 장치다. 그런데 화면이 그 본문을
    버리고 `HTTP 503` 만 보여 주면, 그 장치는 없는 것과 같다. 실제로 화면에서
    503 을 본 사람이 원인을 찾지 못했다.

    두 가지 모양을 모두 받는다.
      `{"code": ..., "message": ...}`            — `shared.http_errors` 가 보내는 것
      `{"detail": {"code": ..., "message": ...}}` — `HTTPException` 이 감싼 것
    """
    try:
        body = response.json()
    except ValueError:
        body = None

    message = None
    if isinstance(body, dict):
        detail = body.get("detail")
        if isinstance(detail, dict):
            message = detail.get("message")
        elif isinstance(detail, str):
            message = detail
        message = message or body.get("message")

    if message:
        return f"{message} (HTTP {response.status_code})"
    return f"API 요청이 실패했습니다. (HTTP {response.status_code})"


def call(project: str, path: str, payload: dict[str, Any]) -> dict[str, Any]:
    try:
        response = httpx.post(f"{api_base(project)}{path}", json=payload, timeout=30.0)
    except httpx.RequestError as error:
        raise WorkflowApiError(
            "API에 연결할 수 없습니다. 해당 FastAPI 서버가 실행 중인지 확인하세요."
        ) from error
    if response.is_error:
        raise WorkflowApiError(explain(response))
    return response.json()


def read(project: str, path: str) -> dict[str, Any]:
    try:
        response = httpx.get(f"{api_base(project)}{path}", timeout=10.0)
    except httpx.RequestError as error:
        raise WorkflowApiError(
            "API에 연결할 수 없습니다. 해당 FastAPI 서버가 실행 중인지 확인하세요."
        ) from error
    if response.is_error:
        raise WorkflowApiError(explain(response))
    return response.json()
