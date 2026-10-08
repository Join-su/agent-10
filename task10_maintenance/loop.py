"""uvicorn 이 쓸 이벤트 루프. **Windows 에서 앱을 띄우려면 필요하다.**

    uv run uvicorn task10_maintenance.app:app --port 8035 --env-file .env --loop task10_maintenance.loop:selector_loop_factory

검토 대기 건 저장소(Postgres)는 psycopg 의 **비동기** 연결을 쓴다. psycopg 는 Windows 의
기본 루프(`ProactorEventLoop`)를 거부한다(`InterfaceError`). uvicorn 은 Windows 에서 기본으로
그 루프를 고르므로, 이 함수로 `SelectorEventLoop` 를 쓰게 한다. macOS·Linux 는 원래 이 루프라
바뀌는 것이 없다. 그래서 어느 OS 에서든 같은 명령을 쓴다.

**제약:** Windows 의 `SelectorEventLoop` 는 하위 Process 를 띄우지 못한다. 그래서 Windows 로컬
실행에서는 `MCP_MODE=on` 을 쓸 수 없다(Docker 에서는 된다). `lookup.py` 가 그 경우 이유를 말한다.
"""
from __future__ import annotations

import asyncio
import sys


def selector_loop_factory() -> asyncio.AbstractEventLoop:
    """uvicorn `--loop` 에 이름으로 지정하는 함수. **루프 인스턴스를 만들어 돌려준다.**

    uvicorn 은 이름으로 지정한 함수를 루프 팩토리 그 자체로 쓴다(인자 없이 불러 루프를 받는다).
    내장 이름(asyncio·uvloop)과 달리 `use_subprocess` 를 넘기지 않는다. 한때 클래스를 돌려주게
    잘못 만들었고, Test 가 실제 uvicorn 설정으로 불러 보고 잡았다.
    """
    return asyncio.SelectorEventLoop()


def windows_proactor_hint(error: BaseException) -> str:
    """psycopg 가 Windows 기본 루프를 거부한 오류면 고치는 방법을, 아니면 빈 문자열을 돌려준다."""
    if "ProactorEventLoop" not in str(error):
        return ""
    return (" Windows 기본 이벤트 루프는 psycopg 비동기 연결을 쓸 수 없습니다. uvicorn 명령 끝에 "
            "--loop task10_maintenance.loop:selector_loop_factory 를 붙여 실행하세요.")


def subprocess_loop() -> asyncio.AbstractEventLoop:
    """하위 Process(MCP 서버)를 띄울 수 있는 루프. Windows 는 Proactor, 그 밖은 Selector.

    앱 서버가 아니라 **Postgres 비동기 연결을 쓰지 않는 곳**(MCP 만 다루는 Test 등)에서 쓴다.
    `asyncio.run(coroutine, loop_factory=subprocess_loop)`
    """
    return asyncio.ProactorEventLoop() if sys.platform == "win32" else asyncio.SelectorEventLoop()
