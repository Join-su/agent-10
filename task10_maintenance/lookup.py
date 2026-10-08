"""이력 담당 Agent — Agent 가 Tool 을 불러 판정과 이력을 모은다.

**루프를 직접 돌리지 않는다.** v2 `shared/tools` 가 조립한 Agent(`create_agent` +
호출 상한)가 돈다. 여기서 하는 일은 도메인 몫뿐이다 — 어떤 Tool 을 쥐여 줄지,
무엇을 물을지, fixture 에서 어떤 순서로 부를지, 그리고 **끝난 뒤 무엇이 일어났는지
기록에서 읽는 것**.

fixture 대본은 무엇을 부를지만 정한다. Tool 은 진짜로 실행된다. 대본이 둘째 턴에
무엇을 부를지 정하려면 판정 결과를 알아야 하므로, 대본을 만들 때 같은 판정을
미리 계산한다. live 에서는 모델이 첫 턴 결과를 보고 스스로 정한다. 응답의
`dependency_respected` 와 `missing_history_types` 가 그것을 지켰는지 보여 준다.
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass

from langchain_core.messages import AIMessage
from langchain_core.tools import BaseTool

from shared.rag.mode import is_live_mode
from shared.tools import agent_model, arun_agent, as_data, build_agent, mcp_tools, stdio_server
from shared.tools.agent import AgentRun
from task10_maintenance.domain import CriterionResult, EventCard, EvidenceItem
from task10_maintenance.criteria import check_criteria, met_types
from task10_maintenance.tools import LOCAL_TOOLS

MCP_SERVER_MODULE = "task10_maintenance.mcp_server"

# 모델이 판단하는 횟수. 정상 경로는 3회(독립 셋 → 이력 → 마무리). 상한은 도달 가능해야 한다.
STEP_BUDGET = 4

SYSTEM_PROMPT = (
    "당신은 MC-01 설비 이상 이벤트의 근거를 모으는 정비 지원 담당자입니다. Tool 로 확인한 값만 씁니다.\n"
    "1. check_criteria, past_false_alarms, last_tool_change 는 서로 독립이므로 첫 턴에 함께 부르세요.\n"
    "2. check_criteria 결과를 본 뒤, 예측 유형과 기준이 성립한 유형마다 same_type_history 를 부르세요.\n"
    "3. before 에는 EventCard 의 detected_at 을 그대로 넣으세요. 값을 지어내지 마세요.\n"
    "4. 원인을 확정하지 마세요. 조회가 끝나면 무엇을 찾았는지만 한 문단으로 적으세요."
)

FIXTURE_NOTE = (
    "fixture 모드에서는 Tool 이 진짜로 실행됩니다(판정 계산·이력 SQL). 대본인 것은 "
    "'모델이 무엇을 부를지 고르는 것' 하나뿐입니다. 모델이 스스로 고르는 것을 보려면 APP_MODE=live."
)


def mcp_enabled() -> bool:
    return os.getenv("MCP_MODE", "off").strip().lower() == "on"


def tool_source() -> str:
    return "mcp" if mcp_enabled() else "local"


async def lookup_tools() -> list[BaseTool]:
    """같은 Tool 을 안에서 얻거나 별도 Process(MCP)에서 얻는다. Agent 쪽 코드는 모른다."""
    if mcp_enabled():
        # 서버의 Tool 이 정비 이력(Postgres)을 읽으므로 DB 주소만 넘긴다.
        return list(await mcp_tools({"history": stdio_server(MCP_SERVER_MODULE, pass_env=("DATABASE_URL",))}))
    return list(LOCAL_TOOLS)


def needed_types(card: EventCard) -> list[str]:
    """이력을 찾아야 하는 유형: 예측 유형 + 판정 기준이 성립한 유형."""
    met = met_types(check_criteria(card.sensor_snapshot, card.quality_grade))
    return list(dict.fromkeys([card.prediction.predicted_failure_type, *sorted(met)]))


def fixture_plan(card: EventCard) -> list[AIMessage]:
    """fixture 에서 모델이 고를 순서. **의존 관계를 그대로 담는다.**"""
    s, before = card.sensor_snapshot, card.detected_at
    sensors = {"air_temperature_k": s.air_temperature_k, "process_temperature_k": s.process_temperature_k,
               "rotational_speed_rpm": s.rotational_speed_rpm, "torque_nm": s.torque_nm,
               "tool_wear_min": s.tool_wear_min, "quality_grade": card.quality_grade}
    first = AIMessage(content="", tool_calls=[
        {"name": "check_criteria", "args": sensors, "id": "c1"},
        {"name": "past_false_alarms", "args": {"predicted_type": card.prediction.predicted_failure_type,
                                               "before": before}, "id": "c2"},
        {"name": "last_tool_change", "args": {"before": before}, "id": "c3"},
    ])
    second = AIMessage(content="", tool_calls=[
        {"name": "same_type_history", "args": {"failure_type": t, "before": before}, "id": f"h{n}"}
        for n, t in enumerate(needed_types(card), start=1)
    ])
    done = AIMessage(content="판정과 이력 조회를 마쳤습니다. (fixture 대본)")
    return [first, second, done]


def question_for(card: EventCard) -> str:
    """모델에게 건네는 것은 EventCard 그대로다. 정답은 들어 있지 않다."""
    return "다음 이상 이벤트의 근거를 모아 주세요.\n" + card.model_dump_json(
        include={"event_id", "detected_at", "quality_grade", "sensor_snapshot", "prediction"})


@dataclass
class Lookup:
    run: AgentRun
    criteria: list[CriterionResult]
    history: list[EvidenceItem]
    needed: list[str]
    history_types: list[str]
    dependency_respected: bool

    @property
    def missing_history_types(self) -> list[str]:
        return [t for t in self.needed if t not in self.history_types]


EXPECTED_KEY = {"check_criteria": "results", "same_type_history": "records",
                "past_false_alarms": "records", "last_tool_change": "records"}


def succeeded(obs) -> bool:
    """호출이 정말 성공했는가. **상태만 보지 않고 결과 모양까지 본다.**

    MCP 를 거치면 서버 쪽 오류(잘못된 인자 등)가 예외가 아니라 "Error executing tool …"
    이라는 정상 결과 글자로 돌아온다. 상태만 보면 실패한 호출을 성공으로 센다.
    """
    return obs.ok and EXPECTED_KEY.get(obs.tool, "summary") in as_data(obs.result)


def read_run(card: EventCard, run: AgentRun) -> Lookup:
    """무슨 일이 있었는지 **기록에서만** 읽는다. 대본을 믿지 않는다."""
    criteria: list[CriterionResult] = []
    history: list[EvidenceItem] = []
    for obs in run.observations:
        data = as_data(obs.result) if succeeded(obs) else {}
        if obs.tool == "check_criteria" and "results" in data:
            criteria = [CriterionResult.model_validate(r) for r in data["results"]]
        for record in data.get("records", []):
            item = EvidenceItem.model_validate(record)
            if all(h.evidence_id != item.evidence_id for h in history):
                history.append(item)

    turn_of: dict[str, list[int]] = {}
    turn = 0
    for message in run.messages:
        if isinstance(message, AIMessage) and message.tool_calls:
            turn += 1
            for call in message.tool_calls:
                turn_of.setdefault(call["name"], []).append(turn)
    criteria_turn = min(turn_of.get("check_criteria", [10**6]))
    history_turns = turn_of.get("same_type_history", [])
    respected = bool(history_turns) and all(t > criteria_turn for t in history_turns)
    history_types = [o.arguments.get("failure_type") for o in run.observations
                     if o.tool == "same_type_history" and succeeded(o)]
    return Lookup(run=run, criteria=criteria, history=history, needed=needed_types(card),
                  history_types=history_types, dependency_respected=respected)


async def lookup(card: EventCard, *, step_budget: int = STEP_BUDGET) -> Lookup:
    agent = build_agent(agent_model(fixture_plan(card)), await lookup_tools(),
                        system_prompt=SYSTEM_PROMPT, step_budget=step_budget)
    run = await arun_agent(agent, question_for(card), step_budget=step_budget)
    return read_run(card, run)


def tool_choice_is_the_model() -> bool:
    return is_live_mode()


def observation_summary(lookup_result: Lookup) -> list[dict]:
    return [{"tool": o.tool, "arguments": o.arguments, "ok": succeeded(o),
             "summary": as_data(o.result).get("summary", o.result[:120]) if succeeded(o) else o.result[:200]}
            for o in lookup_result.run.observations]


def dumps(value) -> str:
    return json.dumps(value, ensure_ascii=False)
