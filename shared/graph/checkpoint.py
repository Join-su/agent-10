"""멈춘 Thread(검토 대기 건)를 어디에 둘 것인가 — **Postgres** 다.

사람 승인을 기다리는 시스템에서 이것은 사소한 설정이 아니다. 저장소가 프로세스
메모리면 재시작 한 번에 승인 대기 중이던 건이 사라진다. **기다리라고 해 놓고
잊는 것**이다. 그래서 매뉴얼 vector·정비 이력과 같은 Postgres(`DATABASE_URL`)에 둔다.

여는 함수가 `async` 인 이유가 있다. 그래프의 노드가 비동기다(MCP Tool 이
비동기 전용이라 그렇다). 그러면 저장소도 비동기여야 한다. 동기 저장소를 비동기
그래프에 물리면 `ainvoke` 에서 `NotImplementedError` 가 난다.

**비동기 연결은 연 이벤트 루프에 묶인다.** uvicorn 은 루프가 하나라 연결도 하나다.
Test 의 `TestClient` 처럼 요청마다 루프가 새로 생기면 그 루프에서 다시 연다. 상태는
DB 에 있으므로 다시 열어도 앞 요청이 멈춰 둔 건을 찾는다.
"""
from __future__ import annotations

import asyncio
import os
from contextlib import AsyncExitStack

from langgraph.checkpoint.base import BaseCheckpointSaver

# 루프마다 저장소 하나. 매 요청마다 새로 열면 연결이 쌓인다.
_STACK: AsyncExitStack | None = None
_STORE: BaseCheckpointSaver | None = None
_LOOP: asyncio.AbstractEventLoop | None = None


class ThreadStoreError(RuntimeError):
    """Thread 저장소를 열 수 없다. 운영자가 고칠 수 있는 상태다."""


def _database_url() -> str:
    return os.getenv("DATABASE_URL", "").strip()


def thread_store_durability() -> str:
    """검토 대기 건이 어디에 남는가. Postgres 라 재시작을 넘긴다."""
    return "postgres"


async def thread_store() -> BaseCheckpointSaver:
    """`DATABASE_URL` 의 Postgres 에 연다. 처음 열 때 저장소 표를 만든다(있으면 그대로 둔다)."""
    global _STORE, _STACK, _LOOP
    loop = asyncio.get_running_loop()
    if _STORE is not None and _LOOP is loop:
        return _STORE

    url = _database_url()
    if not url:
        raise ThreadStoreError(
            "검토 대기 건을 저장하려면 DATABASE_URL 이 필요합니다. DB 를 먼저 띄우세요: docker compose up -d db")

    from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver

    stack = AsyncExitStack()
    try:
        store = await stack.enter_async_context(
            AsyncPostgresSaver.from_conn_string(url.replace("postgresql+psycopg://", "postgresql://", 1)))
        await store.setup()
    except Exception as error:
        await stack.aclose()
        raise ThreadStoreError(
            f"검토 대기 건 저장소(Postgres)를 열 수 없습니다 ({type(error).__name__}). "
            "DB 가 떠 있는지 확인하세요: docker compose ps db"
        ) from error
    _STORE, _STACK, _LOOP = store, stack, loop
    return _STORE


def reset_thread_store() -> None:
    """다음 호출에서 저장소를 다시 연다. **Test 와 설정 변경용이다.**

    열려 있던 연결은 참조만 놓는다. 저장된 상태는 DB 에 있으므로 재시작을 흉내 내는
    데는 문제가 없다.
    """
    global _STORE, _STACK, _LOOP
    _STORE = _STACK = _LOOP = None


async def close_thread_store() -> None:
    """정상 종료 경로. 연결을 닫고 참조를 지운다."""
    global _STORE, _STACK, _LOOP
    if _STACK is not None:
        await _STACK.aclose()
    _STORE = _STACK = _LOOP = None


def graph_config(thread_id: str) -> dict[str, dict[str, str]]:
    """어느 Thread 를 이어 갈지. **이 값이 곧 "같은 건"의 정의다.**"""
    if not thread_id:
        raise ThreadStoreError("thread_id 없이는 멈춘 건을 다시 찾을 수 없습니다.")
    return {"configurable": {"thread_id": thread_id}}
