"""사내 시스템을 별도 Process 에서 표준 방식으로 가져온다.

MCP 서버는 **다른 Process** 다. 그래서 같은 저장소 안에 있어도 import 로 닿지
않고, 서버가 죽으면 우리 앱은 살아 있어야 한다.

`MultiServerMCPClient` 가 Process 를 띄우고 stdio 로 붙고 Tool 목록을 받아
**LangChain Tool 로 바꿔 준다.** 그래서 받아 온 것을 그대로 `create_agent` 에
넣을 수 있다. 한때 이 연결을 직접 만들었는데(별도 Thread 의 event loop, 세션
수명 관리, 응답 payload 풀기) 전부 이 한 줄이 한다.
"""
from __future__ import annotations

import sys
from collections.abc import Mapping, Sequence

from langchain_core.tools import BaseTool


class McpToolsUnavailable(RuntimeError):
    """MCP 서버에서 Tool 을 가져오지 못했다. 고칠 수 있는 상태다."""


def stdio_server(module: str, *, python: str | None = None) -> dict[str, object]:
    """이 저장소의 모듈을 MCP 서버로 띄우는 설정.

    `sys.executable` 을 쓴다. `"python"` 이라고 적으면 가상환경 밖의 해석기가
    잡혀 의존성이 없다는 이유로 서버가 죽는다.
    """
    return {"command": python or sys.executable,
            "args": ["-m", module],
            "transport": "stdio"}


async def mcp_tools(servers: Mapping[str, Mapping[str, object]]) -> Sequence[BaseTool]:
    """붙어서 Tool 목록을 받는다. 실패는 타입으로 구분해 올린다."""
    if not servers:
        raise McpToolsUnavailable("연결할 MCP 서버가 없습니다.")

    from langchain_mcp_adapters.client import MultiServerMCPClient

    try:
        tools = await MultiServerMCPClient(dict(servers)).get_tools()
    except Exception as error:
        raise McpToolsUnavailable(
            f"MCP 서버에 붙지 못했습니다: {type(error).__name__}. "
            f"서버가 단독으로 뜨는지 먼저 확인하세요: {_how_to_check(servers)}"
        ) from error

    if not tools:
        raise McpToolsUnavailable("MCP 서버가 Tool 을 하나도 노출하지 않았습니다.")
    return tools


def _how_to_check(servers: Mapping[str, Mapping[str, object]]) -> str:
    """받는 사람이 다음에 칠 명령. 원인 이름만 주면 무엇을 할지 모른다."""
    commands = []
    for spec in servers.values():
        args = spec.get("args") or []
        module = args[-1] if isinstance(args, (list, tuple)) and args else "<모듈>"
        commands.append(f"uv run python -m {module}")
    return " / ".join(commands)
