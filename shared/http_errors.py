"""설정이 빠졌을 때 API 가 무엇이 빠졌는지 말하게 한다.

키가 없다거나 DB 가 안 떠 있다는 것은 **운영자가 고칠 수 있는 상태**이지
서버 버그가 아니다. 그런데 그대로 두면 FastAPI 가 500 으로 떨어뜨리고 원인은
서버 로그에만 남는다. API 만 보는 쪽에서는 알 길이 없다. 실제로 다른 환경에서
받아 띄운 사람이 500 만 보고 원인을 찾지 못했다.

503 은 "지금은 못 한다, 고치면 된다"는 뜻이다. 그 자리에 무엇이 빠졌는지 담는다.
"""
from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse


def register_unavailable(app: FastAPI, *exception_types: type[Exception], code: str) -> None:
    """지정한 예외를 503 과 사람이 읽을 메시지로 바꾼다.

    넓게 잡으면 안 된다. ``Exception`` 을 통째로 503 으로 만들면 진짜 버그가
    "설정 문제"로 위장되어 아무도 고치지 않는다. 운영자가 고칠 수 있는 타입만
    준다.
    """
    if not exception_types:
        raise ValueError("잡을 예외 타입을 하나 이상 줘야 한다")

    def handler(_: Request, error: Exception) -> JSONResponse:
        return JSONResponse(
            status_code=503,
            content={"code": code, "message": str(error) or type(error).__name__},
        )

    for exception_type in exception_types:
        app.add_exception_handler(exception_type, handler)
