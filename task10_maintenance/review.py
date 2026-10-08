"""이상 이벤트 하나를 사람 검토까지 데려가는 그래프. **이 앱의 본체다.**

    ┌ collect_manual  ┐
    │                 ├─▶ merge ─▶ decide ─┬─ grounded_draft ─▶ draft ──┐
    └ collect_history ┘                    ├─ escalation ─────▶ escalate ├─▶ validate ─┬─ (오류, 한 번 더) ─▶ draft
                                           └─ inspect_only ───▶ inspect ─┘             └─▶ review (멈춤)
                                                                                              ├─ approve·escalate ─▶ report
                                                                                              ├─ revise ─▶ draft
                                                                                              └─ reject ─▶ close

    collect_manual   매뉴얼 근거 — 하이브리드 검색(`evidence.py`) + 판정 기준·점검 절차 절
    collect_history  정비 이력 — Tool Agent(`lookup.py`), 빠뜨린 유형은 코드가 채운다
    decide           처리 경로 — SOP-EA-01 규칙(`routing.py`). LLM 에게 묻지 않는다
    draft            원인 후보·점검 단계 문장 — LLM(`drafting.py`). grounded_draft 일 때만
    validate         초안 검사(`routing.py::validate_response`). 오류가 있으면 한 번 더 쓴다
    review           **실행이 끊긴다.** 사람이 결정해야 이어 간다
    report           보고서(`report.py`)

**검사 오류가 있는 초안은 승인할 수 없다.** review 노드가 다시 묻는 것으로 막고, 앱은
그보다 먼저 422 로 막는다. 둘 다 두는 것은 앱을 거치지 않고 그래프를 부르는 길이 있기
때문이다.

review 노드는 재개될 때 **처음부터 다시 돈다**(LangGraph 의 interrupt 동작). 그래서
interrupt 앞에는 다시 돌아도 되는 일(packet 만들기)만 둔다. 알림 전송 같은 일을
여기 두면 두 번 나간다.

**이 그래프는 설비를 제어하지 않는다.** 보고서까지다.
"""
from __future__ import annotations

import copy
import operator
from typing import Annotated, Any, TypedDict

from langgraph.checkpoint.serde.base import maybe_add_typed_methods
from langgraph.checkpoint.serde.jsonplus import JsonPlusSerializer
from langgraph.graph import END, START, StateGraph
from langgraph.types import interrupt

from task10_maintenance.criteria import check_criteria, describe, met_types
from task10_maintenance.domain import (
    AgentResponse,
    CauseCandidate,
    CompletedRepair,
    CriterionResult,
    EventCard,
    EvidenceItem,
    InspectionStep,
    MaintenanceReport,
    ReviewDecision,
)
from task10_maintenance.drafting import TYPE_SECTION, DraftParseError, write_draft
from task10_maintenance.evidence import find_evidence, manual_section
from task10_maintenance.history import history_store
from task10_maintenance.lookup import lookup, observation_summary
from task10_maintenance.report import build_report, render_markdown
from task10_maintenance.routing import decide_route, parts_to_prepare, validate_response

MAX_ATTEMPTS = 2      # 초안은 처음 한 번 + 검증 오류를 받고 한 번 더
MAX_REVISIONS = 2     # 검토자가 수정을 요청할 수 있는 횟수. 넘으면 escalate 만 남는다
DECISIONS = ("approve", "revise", "escalate", "reject")

# 멈춘 상태를 저장소에 넣고 꺼낼 때 허용할 타입. 등록하지 않으면 LangGraph 가 경고하고,
# 다음 버전부터는 꺼내기를 막는다.
ALLOWED_TYPES = [("task10_maintenance.domain", name) for name in (
    "EventCard", "EvidenceItem", "CriterionResult", "CauseCandidate", "InspectionStep",
    "AgentResponse", "ReviewDecision", "MaintenanceReport", "CompletedRepair")]


class CaseState(TypedDict, total=False):
    card: EventCard
    completed_repairs: list[CompletedRepair]
    manual_found: Annotated[list[EvidenceItem], operator.add]     # 병렬 담당 둘이 각자 쓴다
    history_found: Annotated[list[EvidenceItem], operator.add]
    queries: list[dict]
    filled_history_types: list[str]
    tool_calls: list[dict]
    criteria: list[CriterionResult]
    evidence: list[EvidenceItem]
    route: str
    reasons: list[str]
    candidates: list[CauseCandidate]
    steps: list[InspectionStep]
    drafted_by: str
    attempts: int
    errors: list[str]
    response: AgentResponse
    decision: ReviewDecision
    revisions: int
    report: MaintenanceReport
    report_markdown: str
    status: str
    trace: Annotated[list[str], operator.add]


# --- 병렬로 근거 모으기 -------------------------------------------------------------

def collect_manual(state: CaseState) -> CaseState:
    """매뉴얼 담당. 검색에 더해, 판정 기준 절·점검 절차 절을 ID 로 바로 붙인다.

    검색이 놓쳐도 초안이 인용할 근거가 있어야 하기 때문이다.
    """
    card = state["card"]
    queries, found, per_query = find_evidence(card)
    for c in check_criteria(card.sensor_snapshot, card.quality_grade):
        if c.met or c.failure_type == card.prediction.predicted_failure_type:
            extra = [manual_section(c.citation, f"{c.failure_type} 판정 기준 절")]
            if c.met:
                extra += [manual_section(TYPE_SECTION[c.failure_type] + s, f"{c.failure_type} {n} 절")
                          for s, n in ((".3", "점검 절차"), (".4", "권장 조치"))]
            found += [e for e in extra if e is not None]
    return {"manual_found": found,
            "queries": [{"label": label, "text": text, "citations": per_query[label]}
                        for label, text in queries],
            "trace": ["collect_manual"]}


async def collect_history(state: CaseState) -> CaseState:
    """이력 담당. Tool Agent 를 부르고, 빠뜨린 유형은 코드가 채운다.

    live 에서 실제 모델은 순서는 지켜도 필요한 유형을 빠뜨렸다. 무엇을 채웠는지는
    `filled_history_types` 에 남긴다.
    """
    card = state["card"]
    looked = await lookup(card)
    found = list(looked.history)
    filled = list(looked.missing_history_types)
    for failure_type in filled:
        found += history_store().same_type_recent(failure_type, card.detected_at)
    return {"history_found": found, "filled_history_types": filled,
            "tool_calls": observation_summary(looked),
            "trace": [f"collect_history(Tool {len(looked.run.tools_called)}회"
                      + (f", 보충 {filled})" if filled else ")")]}


def merge(state: CaseState) -> CaseState:
    """두 담당의 결과를 합친다. 같은 근거는 한 번만 남긴다. 판정은 코드가 다시 한다."""
    card = state["card"]
    evidence: list[EvidenceItem] = []
    for item in state.get("history_found", []) + state.get("manual_found", []):
        if all(e.evidence_id != item.evidence_id for e in evidence):
            evidence.append(item)
    return {"criteria": check_criteria(card.sensor_snapshot, card.quality_grade), "evidence": evidence,
            "attempts": 0, "revisions": state.get("revisions", 0), "trace": ["merge"]}


# --- 경로 -----------------------------------------------------------------------

def decide(state: CaseState) -> CaseState:
    route, reasons = decide_route(state["card"], state["criteria"], state["evidence"],
                                  state.get("completed_repairs", []))
    return {"route": route, "reasons": reasons, "trace": [f"decide:{route}{reasons or ''}"]}


def route_of(state: CaseState) -> str:
    return state["route"]


# --- 경로별 결과 ------------------------------------------------------------------

async def draft(state: CaseState) -> CaseState:
    """LLM 이 문장을 쓴다. 앞선 검증 오류(또는 검토자의 수정 요청)가 있으면 그것을 보고 다시 쓴다."""
    attempts = state.get("attempts", 0) + 1
    feedback = state.get("errors") if (attempts > 1 or state.get("revisions")) else None
    try:
        output, drafted_by = await write_draft(state["card"], state["criteria"], state["evidence"], feedback)
        return {"candidates": output.cause_candidates, "steps": output.inspection_steps,
                "drafted_by": drafted_by, "attempts": attempts, "trace": [f"draft#{attempts}"]}
    except DraftParseError as error:
        return {"candidates": [], "steps": [], "drafted_by": "llm", "attempts": attempts,
                "errors": [str(error)], "trace": [f"draft#{attempts}(형식 오류)"]}


def _add(evidence: list[EvidenceItem], item: EvidenceItem | None) -> list[EvidenceItem]:
    if item is not None and all(e.evidence_id != item.evidence_id for e in evidence):
        evidence.append(item)
    return evidence


def escalate(state: CaseState) -> CaseState:
    """사람에게 넘긴다. 원인을 쓰지 않고, 사유와 확인한 근거만 남긴다(SOP-EA-01 6장)."""
    evidence = _add(list(state["evidence"]), manual_section("SOP-EA-01 6", "escalation 조건 절"))
    return {"candidates": [], "steps": [], "drafted_by": "code", "evidence": evidence,
            "trace": ["escalate"]}


def inspect(state: CaseState) -> CaseState:
    """판정 기준에 해당하지 않는 경고. 원인을 주장하지 않고 오탐 점검을 권한다(SOP-EA-01 8장)."""
    card = state["card"]
    evidence = _add(list(state["evidence"]), manual_section("SOP-EA-01 8", "오탐 처리 절"))
    predicted = next(c for c in state["criteria"] if c.failure_type == card.prediction.predicted_failure_type)
    steps = [InspectionStep(order=1, instruction=f"판정 기준을 수치로 다시 확인한다 — {describe(predicted)}",
                            evidence_ids=[predicted.citation]),
             InspectionStep(order=2, instruction="육안·청음 점검 후 이상이 없으면 오탐 점검 기록을 남긴다",
                            evidence_ids=["SOP-EA-01 8"])]
    past = [e.evidence_id for e in evidence if e.reason.startswith("같은 예측")]
    if past:
        steps.append(InspectionStep(order=3, instruction="같은 예측 유형의 과거 오탐 점검 기록과 비교한다",
                                    evidence_ids=past[:2]))
    return {"candidates": [], "steps": steps, "drafted_by": "code", "evidence": evidence,
            "trace": ["inspect"]}


# --- 검사 -----------------------------------------------------------------------

def validate(state: CaseState) -> CaseState:
    """조립하고 검사한다. 부품은 코드가 근거에서 뽑는다."""
    card = state["card"]
    met = met_types(state["criteria"])
    response = AgentResponse(
        event_id=card.event_id, route=state["route"], criteria_check=state["criteria"],
        evidence=state["evidence"],
        escalation_reasons=state["reasons"] if state["route"] == "escalation" else [],
        cause_candidates=state.get("candidates", []), inspection_steps=state.get("steps", []),
        parts_to_prepare=parts_to_prepare(state["evidence"], met) if state["route"] == "grounded_draft" else [],
        drafted_by=state.get("drafted_by", "code"))
    errors = (state.get("errors", []) if state.get("trace", [""])[-1].endswith("(형식 오류)") else []) \
        + validate_response(response)
    return {"response": response, "errors": errors,
            "trace": ["validate:" + ("통과" if not errors else f"오류 {len(errors)}")]}


def after_validate(state: CaseState) -> str:
    """오류가 있는 초안은 한 번 더 쓴다. 횟수에 상한이 있다. 끝나면 사람에게 간다."""
    if state["errors"] and state["route"] == "grounded_draft" and state.get("attempts", 0) < MAX_ATTEMPTS:
        return "draft"
    return "review"


# --- 사람 ------------------------------------------------------------------------

def packet_of(state: CaseState) -> dict[str, Any]:
    """사람에게 보여 줄 것. 결정에 필요한 것을 담는다."""
    r = state["response"]
    return {
        "event_id": r.event_id, "route": r.route, "escalation_reasons": r.escalation_reasons,
        "criteria": [describe(c) for c in r.criteria_check],
        "cause_candidates": [c.model_dump() for c in r.cause_candidates],
        "inspection_steps": [s.model_dump() for s in r.inspection_steps],
        "parts_to_prepare": r.parts_to_prepare,
        "evidence": [e.model_dump() for e in r.evidence],
        "validation_errors": state.get("errors", []), "drafted_by": r.drafted_by,
        "revisions": state.get("revisions", 0),
        "allowed_decisions": allowed_decisions(state),
    }


def allowed_decisions(state: CaseState) -> list[str]:
    """이 초안에 내릴 수 있는 결정. 검사 오류가 있으면 승인할 수 없다."""
    allowed = ["escalate", "reject"]
    if not state.get("errors"):
        allowed.insert(0, "approve")
    if state["response"].route == "grounded_draft" and state.get("revisions", 0) < MAX_REVISIONS:
        allowed.append("revise")
    return allowed


def review(state: CaseState) -> CaseState:
    """**여기서 실행이 끊긴다.** 재개되면 이 함수가 처음부터 다시 돈다.

    받을 수 없는 결정이 오면 예외를 던지지 않고 **다시 묻는다.** 예외를 던지면 그
    결정값이 저장되어, 올바른 결정을 다시 넣어도 저장된 값이 재생되며 같은 예외가
    난다. 건이 굳는다(Notebook 11 이 재현한다).
    """
    packet = packet_of(state)
    answer = interrupt(packet)
    while (problem := refusal(state, answer)) is not None:
        answer = interrupt({**packet, "refused": answer, "message": problem})
    decision = answer if isinstance(answer, ReviewDecision) else ReviewDecision.model_validate(answer)
    update: CaseState = {"decision": decision, "trace": [f"review:{decision.decision}"]}
    if decision.decision == "revise":
        update["revisions"] = state.get("revisions", 0) + 1
        update["attempts"] = 0
        update["errors"] = [f"검토자 수정 요청: {decision.note or '사유 미기재'}"]
    return update


def refusal(state: CaseState, answer: Any) -> str | None:
    """받을 수 없는 결정이면 그 이유를, 받을 수 있으면 None 을 돌려준다."""
    try:
        decision = answer if isinstance(answer, ReviewDecision) else ReviewDecision.model_validate(answer)
    except Exception as error:   # 형식이 틀린 결정
        return f"결정 형식이 맞지 않습니다: {type(error).__name__}"
    allowed = allowed_decisions(state)
    if decision.decision not in allowed:
        return f"이 초안에는 {decision.decision} 을 할 수 없습니다. 가능한 결정: {allowed}"
    return None


def after_review(state: CaseState) -> str:
    return {"approve": "report", "escalate": "report", "revise": "draft", "reject": "close"}[
        state["decision"].decision]


def report(state: CaseState) -> CaseState:
    made = build_report(state["card"], state["response"], state["decision"])
    return {"report": made, "report_markdown": render_markdown(made), "status": "reported",
            "trace": ["report"]}


def close(state: CaseState) -> CaseState:
    return {"status": "rejected", "trace": ["close"]}


# --- 조립 -----------------------------------------------------------------------

def build_case_graph(checkpointer):
    graph = StateGraph(CaseState)
    for name, node in (("collect_manual", collect_manual), ("collect_history", collect_history),
                       ("merge", merge), ("decide", decide), ("draft", draft), ("escalate", escalate),
                       ("inspect", inspect), ("validate", validate), ("review", review),
                       ("report", report), ("close", close)):
        graph.add_node(name, node)
    graph.add_edge(START, "collect_manual")          # 두 담당은 서로를 기다리지 않는다
    graph.add_edge(START, "collect_history")
    graph.add_edge("collect_manual", "merge")
    graph.add_edge("collect_history", "merge")
    graph.add_edge("merge", "decide")
    graph.add_conditional_edges("decide", route_of, {"grounded_draft": "draft", "escalation": "escalate",
                                                     "inspect_only": "inspect"})
    for name in ("draft", "escalate", "inspect"):
        graph.add_edge(name, "validate")
    graph.add_conditional_edges("validate", after_validate, {"draft": "draft", "review": "review"})
    graph.add_conditional_edges("review", after_review, {"report": "report", "draft": "draft",
                                                         "close": "close"})
    graph.add_edge("report", END)
    graph.add_edge("close", END)
    return graph.compile(checkpointer=strict_copy(checkpointer))


def strict_copy(checkpointer):
    """허용 타입을 명시한 직렬화기를 단 저장소 사본. 공용 저장소는 바꾸지 않는다.

    `with_allowlist` 를 쓰지 않는 이유: 기본(관대) 모드의 직렬화기는 모든 타입을
    경고와 함께 허용하므로, 거기에 목록을 더해도 아무것도 바뀌지 않는다(경고가 그대로
    남는다). 여기서는 목록을 명시해 엄격 모드로 둔다. 목록 밖 타입은 지금부터 막힌다.
    """
    clone = copy.copy(checkpointer)
    clone.serde = maybe_add_typed_methods(JsonPlusSerializer(allowed_msgpack_modules=ALLOWED_TYPES))
    return clone


def start_input(card: EventCard, completed_repairs: list[CompletedRepair]) -> CaseState:
    return {"card": card, "completed_repairs": completed_repairs, "trace": [], "status": "awaiting_review"}
