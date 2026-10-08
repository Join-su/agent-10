"""관찰 → 판단 → 행동 루프를 조립한다.

루프를 직접 돌리지 않는다. `create_agent` 가 만든 그래프가 돈다. 우리가 하는
일은 **무엇을 쓸 수 있는지 주고, 무엇이 일어났는지 읽는 것**이다.

`create_react_agent` 가 아니라 `langchain.agents.create_agent` 를 쓴다. 전자는
LangGraph v1.0 에서 옮겨 갔고 v2.0 에서 사라진다. 지워질 이름을 가르치지 않는다.
"""
from __future__ import annotations

import json
from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any

from langchain.agents import create_agent
from langchain.agents.middleware import ModelCallLimitMiddleware
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage, ToolMessage
from langchain_core.tools import BaseTool

# 한 요청에서 모델이 판단할 수 있는 횟수. 없으면 같은 Tool 을 영원히 부른다.
DEFAULT_STEP_BUDGET = 6


@dataclass
class Observation:
    """Tool 한 번 호출의 결과. **응답에 싣는 것은 이 기록이지 상수가 아니다.**"""

    tool: str
    arguments: dict[str, Any]
    result: str
    ok: bool


@dataclass
class AgentRun:
    answer: str
    observations: list[Observation] = field(default_factory=list)
    steps: int = 0
    step_budget: int = DEFAULT_STEP_BUDGET
    budget_exhausted: bool = False
    messages: list[BaseMessage] = field(default_factory=list)

    @property
    def tools_called(self) -> list[str]:
        return [o.tool for o in self.observations]


def build_agent(model: BaseChatModel, tools: Sequence[BaseTool], *,
                system_prompt: str | None = None,
                step_budget: int = DEFAULT_STEP_BUDGET):
    """Tool 을 쥔 Agent 를 만든다. 루프도 상한도 라이브러리가 맡는다.

    상한을 `recursion_limit` 산수로 흉내 내지 않는다. 한 번 그렇게 했다가
    "Tool 이 몇 번 돌았는가"와 "광고한 상한"이 어긋났다. `recursion_limit` 은
    그래프의 안전장치이지 업무 상한이 아니다.

    `ModelCallLimitMiddleware` 가 **모델이 판단하는 횟수**를 센다. 그것이 이
    루프에서 "몇 번까지 다시 볼 것인가"의 정확한 단위다. 상한에 닿으면
    `exit_behavior="end"` 로 조용히 끝나고, 그 사실은 마지막 메시지가 말해 준다.
    """
    if not tools:
        raise ValueError("Tool 이 하나도 없으면 Agent 를 만들 이유가 없습니다.")
    if step_budget < 1:
        raise ValueError("상한은 1 이상이어야 합니다.")
    return create_agent(
        model, list(tools), system_prompt=system_prompt,
        middleware=[ModelCallLimitMiddleware(run_limit=step_budget, exit_behavior="end")],
    )


def run_agent(agent, question: str, *, step_budget: int = DEFAULT_STEP_BUDGET) -> AgentRun:
    """한 번 돌리고 무슨 일이 있었는지 기록으로 돌려준다.

    상한을 **도달 가능한 값**으로 둔다. 한때 상한이 실제 최대 호출 수보다 커서
    "상한 소진" 상태가 존재할 수 없었고, 그것을 검증하는 Test 는 통과하고 있었다.
    여기서는 `recursion_limit` 이 상한을 실제로 강제한다.
    """
    try:
        state = agent.invoke(*_invocation(question, step_budget))
    except Exception as error:
        return _exhausted_or_raise(error, step_budget)
    return _finish(list(state["messages"]), step_budget)


async def arun_agent(agent, question: str, *,
                     step_budget: int = DEFAULT_STEP_BUDGET) -> AgentRun:
    """같은 일을 비동기로. **MCP Tool 은 비동기 전용**이라 이 길이 필요하다.

    MCP 어댑터가 돌려주는 Tool 은 `coroutine` 만 갖는다. 동기로 부르면 실행
    자체가 안 된다. 그래서 MCP 를 쓰는 경로는 끝까지 비동기다.
    """
    try:
        state = await agent.ainvoke(*_invocation(question, step_budget))
    except Exception as error:
        return _exhausted_or_raise(error, step_budget)
    return _finish(list(state["messages"]), step_budget)


def _invocation(question: str, step_budget: int):
    """업무 상한은 middleware 가 센다. `recursion_limit` 은 그 바깥의 안전장치다.

    넉넉히 준다. 여기 걸리면 상한 문제가 아니라 그래프가 이상한 것이다.
    """
    return ({"messages": [("user", question)]},
            {"recursion_limit": step_budget * 4 + 10})


def _exhausted_or_raise(error: Exception, step_budget: int) -> AgentRun:
    """그래프 안전장치에 걸린 것도 소진으로 본다. 나머지는 버그이므로 올린다."""
    if type(error).__name__ != "GraphRecursionError":
        raise error
    return AgentRun(answer="", step_budget=step_budget, budget_exhausted=True)


def _finish(messages: list[BaseMessage], step_budget: int) -> AgentRun:
    """소진 여부를 **셈으로** 판정한다. 라이브러리의 안내 문구를 읽지 않는다.

    상한이 `run_limit=N` 이면 모델은 많아야 N 번 불린다. 정상 종료는 *Tool 을
    부른 턴* + *답을 쓴 한 번* 이므로 Tool 을 부른 턴은 많아야 N-1 이다. 그러니
    **Tool 을 부른 턴이 정확히 N 이면 답을 쓸 차례가 오지 않은 것**이고, 그것이
    소진이다.

    영어 안내 문구("Model call limits exceeded...")를 문자열로 찾지 않는다.
    라이브러리가 문구를 바꾸면 조용히 소진을 성공으로 보고하게 된다. 그리고 그
    문구를 답변으로 내보내지도 않는다. 고객이 읽을 글이 아니다.
    """
    steps = sum(1 for m in messages if isinstance(m, AIMessage) and m.tool_calls)
    exhausted = steps >= step_budget
    return AgentRun(
        answer="" if exhausted else _final_answer(messages),
        observations=_observations(messages),
        steps=steps,
        step_budget=step_budget,
        budget_exhausted=exhausted,
        messages=messages,
    )


def _observations(messages: Sequence[BaseMessage]) -> list[Observation]:
    """무엇을 어떤 인자로 불렀고 무엇이 돌아왔는지. 실제 메시지에서만 읽는다."""
    requested: dict[str, dict[str, Any]] = {}
    for message in messages:
        if isinstance(message, AIMessage):
            for call in message.tool_calls:
                requested[str(call["id"])] = {"name": call["name"], "args": call["args"]}

    found: list[Observation] = []
    for message in messages:
        if not isinstance(message, ToolMessage):
            continue
        asked = requested.get(str(message.tool_call_id), {})
        found.append(Observation(
            tool=str(asked.get("name") or message.name or "?"),
            arguments=dict(asked.get("args") or {}),
            result=as_text(message.content),
            ok=message.status != "error",
        ))
    return found


def as_text(content: Any) -> str:
    """Tool 결과를 한 가지 모양으로 만든다.

    같은 Tool 인데 부르는 경로에 따라 모양이 다르다. 안에서 부르면 문자열이고,
    MCP 로 부르면 `[{"type": "text", "text": ...}]` 꼴의 블록 목록이다. 화면과
    Test 가 두 모양을 각각 다루게 두면, 경로를 바꾼 순간 조용히 깨진다.
    """
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = [str(block.get("text", "")) if isinstance(block, dict) else str(block)
                 for block in content]
        return "\n".join(p for p in parts if p)
    return str(content)


def _final_answer(messages: Sequence[BaseMessage]) -> str:
    for message in reversed(messages):
        if isinstance(message, AIMessage) and not message.tool_calls:
            return str(message.content)
    return ""


def as_data(result: Any) -> dict[str, Any]:
    """dict 를 돌려주는 Tool 의 결과를 경로와 무관하게 dict 로 받는다.

    안에서 부르면 dict 그대로 오지만, MCP 로 부르면 그 dict 를 JSON 으로 찍은
    **문자열 블록**이 온다. 판단 로직이 두 모양을 각각 다루면, 경로를 바꾼
    순간 규칙이 조용히 어긋난다. 숫자로 판단하는 곳에서는 그 어긋남이 곧
    잘못된 심사다.
    """
    if isinstance(result, dict):
        return result
    text = as_text(result).strip()
    if not text:
        return {}
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        return {"summary": text}
    return parsed if isinstance(parsed, dict) else {"summary": text}
