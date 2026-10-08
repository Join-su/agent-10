"""멈춘 Thread 를 어디에 둘 것인가.

사람 승인을 기다리는 시스템에서 이것은 사소한 설정이 아니다. 저장소가 프로세스
메모리면 재시작 한 번에 승인 대기 중이던 심사가 사라진다. **기다리라고 해 놓고
잊는 것**이다. 그래서 어느 쪽인지 진단에 드러낸다.

여는 함수가 `async` 인 이유가 있다. 그래프의 노드가 비동기다(MCP Tool 이
비동기 전용이라 그렇다). 그러면 파일 저장소도 비동기여야 한다. 동기
`SqliteSaver` 를 비동기 그래프에 물리면 `ainvoke` 에서 `NotImplementedError` 가
난다. 절반만 비동기인 구성은 돌지 않는다.
"""
from __future__ import annotations

import os
from contextlib import AsyncExitStack
from pathlib import Path

from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.checkpoint.memory import InMemorySaver

# 저장소는 프로세스가 사는 동안 하나만 둔다. 매 요청마다 새로 열면 연결이
# 쌓이고, 더 나쁘게는 앞 요청이 멈춰 둔 Thread 를 못 찾는다.
_STACK: AsyncExitStack | None = None
_STORE: BaseCheckpointSaver | None = None


class ThreadStoreError(RuntimeError):
    """Thread 저장소를 열 수 없다. 운영자가 고칠 수 있는 상태다."""


def thread_db_path() -> str:
    return os.getenv("THREAD_DB", "").strip()


def thread_store_durability() -> str:
    """`file` 이면 재시작을 넘긴다. `process_lifetime` 이면 넘기지 못한다."""
    return "file" if thread_db_path() else "process_lifetime"


async def thread_store() -> BaseCheckpointSaver:
    """`THREAD_DB` 가 있으면 파일에, 없으면 메모리에 둔다.

    파일 저장소도 라이브러리가 준다. 한때 `langgraph-checkpoint-sqlite` 가
    직렬화 API 와 맞지 않아 `BaseCheckpointSaver` 를 237줄로 직접 구현했고 그
    근거를 파일에 적어 두었다. 3.1.1 에서 고쳐졌으므로 근거가 사라졌고, 수제
    구현을 지웠다.
    """
    global _STORE, _STACK
    if _STORE is not None:
        return _STORE

    path = thread_db_path()
    if not path:
        _STORE = InMemorySaver()
        return _STORE

    from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver

    try:
        target = Path(path).expanduser()
        target.parent.mkdir(parents=True, exist_ok=True)
        _STACK = AsyncExitStack()
        _STORE = await _STACK.enter_async_context(
            AsyncSqliteSaver.from_conn_string(str(target)))
    except Exception as error:
        _STACK = None
        raise ThreadStoreError(
            f"THREAD_DB 경로를 열 수 없습니다: {path} ({type(error).__name__}). "
            "쓸 수 있는 경로인지 확인하거나 THREAD_DB 를 비워 메모리 저장소로 두세요."
        ) from error
    return _STORE


def reset_thread_store() -> None:
    """다음 호출에서 저장소를 다시 연다. **Test 와 설정 변경용이다.**

    열려 있던 연결은 참조만 놓는다. 여기서 닫으려면 이 함수가 비동기가 되어야
    하고, 그러면 설정을 바꾸는 모든 자리가 비동기가 된다. 대신 파일에 쓴 것은
    이미 파일에 있으므로 재시작을 흉내 내는 데는 문제가 없다.
    """
    global _STORE, _STACK
    _STORE = None
    _STACK = None


async def close_thread_store() -> None:
    """정상 종료 경로. 연결을 닫고 참조를 지운다."""
    global _STORE, _STACK
    if _STACK is not None:
        await _STACK.aclose()
    _STORE = None
    _STACK = None


def graph_config(thread_id: str) -> dict[str, dict[str, str]]:
    """어느 Thread 를 이어 갈지. **이 값이 곧 "같은 심사"의 정의다.**"""
    if not thread_id:
        raise ThreadStoreError("thread_id 없이는 멈춘 심사를 다시 찾을 수 없습니다.")
    return {"configurable": {"thread_id": thread_id}}
