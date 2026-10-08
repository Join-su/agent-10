"""STEP 05 가 쌓는 Tool 계층.

STEP 03·04 가 `shared/rag` 에 검색을 쌓았다. 여기서는 **바깥 시스템을 부르는
법**을 쌓는다. STEP 06 의 그래프 노드가 이 Tool 들을 그대로 부른다.

**하나도 손으로 만들지 않는다.**

| 하는 일 | 쓰는 것 |
|---|---|
| Tool 선언과 인자 검증 | `langchain_core.tools.tool` (`StructuredTool`) |
| Tool 호출 루프 | `langchain.agents.create_agent` |
| 별도 Process 의 MCP 서버 연결 | `langchain_mcp_adapters.client.MultiServerMCPClient` |

한때 이 셋을 전부 손으로 만들어 두었다. JSON 스키마를 dict 로 적고, 인자를
직접 검증하고, 호출 루프를 while 로 돌리고, MCP stdio 세션을 별도 Thread 로
감쌌다. 동작은 했지만 학습자가 실무에서 쓸 이름을 하나도 배우지 못한다.
"""
from shared.tools.agent import (
    AgentRun,
    Observation,
    arun_agent,
    as_data,
    as_text,
    build_agent,
    run_agent,
)
from shared.tools.mcp import McpToolsUnavailable, mcp_tools, stdio_server
from shared.tools.model import ScriptedToolModel, agent_model

__all__ = [
    "AgentRun", "Observation", "build_agent", "run_agent", "arun_agent",
    "as_text", "as_data",
    "McpToolsUnavailable", "mcp_tools", "stdio_server",
    "ScriptedToolModel", "agent_model",
]
