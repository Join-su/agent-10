"""정비 이력 시스템을 MCP 로 여는 서버. **별도 Process** 에서 stdio 로 돈다.

    uv run python -m task10_maintenance.mcp_server

노출할 Tool 을 여기서 다시 적지 않는다. `tools.py` 의 읽기 전용 목록에서 그대로
가져와 등록한다. 같은 Tool 을 두 곳에 적으면 한쪽만 고쳐져 두 경로가 다르게 돈다.
"""
from __future__ import annotations

from mcp.server.fastmcp import FastMCP

from task10_maintenance.tools import LOCAL_TOOLS, READ_ONLY_TOOLS

server = FastMCP("maintenance-history-readonly")

for _tool in LOCAL_TOOLS:
    if _tool.name not in READ_ONLY_TOOLS:      # 읽기 전용 목록 밖은 열지 않는다
        raise RuntimeError(f"읽기 전용 목록에 없는 Tool 을 열려고 했습니다: {_tool.name}")
    server.add_tool(_tool.func, name=_tool.name, description=_tool.description)


if __name__ == "__main__":
    server.run()
