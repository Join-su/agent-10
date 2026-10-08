"""과제 10 앱이 실제로 하는 일을 검증한다.

    uv run python -m pytest task10_maintenance/tests -q

v2 의 원칙대로 **실패할 수 있는 테스트**만 둔다. 판정 기준을 한 글자 바꾸면
AI4I 1만 행과의 대조가 깨지고, 경로 규칙을 바꾸면 대표 사례 10건 중 하나가 깨진다.

fixture 에서 진짜인 것: 판정 계산, 이력 SQL, Tool 실행, 매뉴얼 검색 순위(녹화된 실제
임베딩), 경로, 검사, 멈춤과 재개. 대본인 것: 이력 Agent 가 무엇을 부를지 고르는 것,
초안 문장 두 가지뿐이다.
"""
from __future__ import annotations

import asyncio
import json
import sqlite3
from contextlib import closing
from datetime import datetime, timedelta
from itertools import cycle
from pathlib import Path

import pandas as pd
import pytest
from fastapi.testclient import TestClient
from langchain_core.language_models import GenericFakeChatModel
from langchain_core.messages import AIMessage
from langchain_core.messages.tool import ToolMessage
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.types import Command

from shared.graph.checkpoint import reset_thread_store
from shared.tools import ScriptedToolModel, build_agent, mcp_tools, stdio_server
from shared.tools.agent import AgentRun, Observation, run_agent
from task10_maintenance import app as app_module
from task10_maintenance import drafting
from task10_maintenance import review as review_module
from task10_maintenance.app import create_app
from task10_maintenance.criteria import check_criteria, met_types
from task10_maintenance.domain import (
    AgentResponse,
    CauseCandidate,
    CompletedRepair,
    EventCard,
    EvidenceItem,
    InspectionStep,
    ReviewDecision,
    SensorSnapshot,
)
from task10_maintenance.evaluation import evaluate, route_for, scenarios
from task10_maintenance.evidence import (
    NotRecorded,
    card_queries,
    find_evidence,
    load_cards,
    load_chunks,
    recorded_embeddings,
)
from task10_maintenance.history import HistoryStore
from task10_maintenance.lookup import (
    MCP_SERVER_MODULE,
    STEP_BUDGET,
    fixture_plan,
    lookup,
    question_for,
    read_run,
)
from task10_maintenance.mcp_server import server as mcp_server
from task10_maintenance.report import NotAReport, build_report, render_markdown
from task10_maintenance.review import MAX_ATTEMPTS, MAX_REVISIONS, build_case_graph, start_input
from task10_maintenance.routing import decide_route, parts_to_prepare, validate_response
from task10_maintenance.tools import LOCAL_TOOLS, READ_ONLY_TOOLS, same_type_history
from task10_maintenance.tools import check_criteria as criteria_tool

DATA = Path(__file__).resolve().parents[1] / "data"
ENGINEER = {"reviewer_role": "정비 기술자"}
SECTION = {"TWF": "MC01-MM 4.1", "HDF": "MC01-MM 4.2", "PWF": "MC01-MM 4.3", "OSF": "MC01-MM 4.4"}


@pytest.fixture(autouse=True)
def fixture_mode(monkeypatch):
    """셸에 live·MCP 설정이 있어도 테스트는 fixture 로 돈다. OpenAI 를 부르지 않는다."""
    for name in ("APP_MODE", "OPENAI_API_KEY", "MCP_MODE", "THREAD_DB", "VECTOR_BACKEND", "HISTORY_BACKEND"):
        monkeypatch.delenv(name, raising=False)
    reset_thread_store()
    app_module.reset_graph()
    yield
    reset_thread_store()
    app_module.reset_graph()


def _scenario(sid: str) -> dict:
    return next(s for s in scenarios() if s["scenario_id"] == sid)


def _card(sid_or_event: str) -> EventCard:
    if sid_or_event.startswith("S"):
        return EventCard.model_validate(_scenario(sid_or_event)["card"])
    return load_cards()[sid_or_event]


@pytest.fixture(scope="module")
def store() -> HistoryStore:
    return HistoryStore()


# =============================================================================
# 판정 기준 — 모델의 예측과 별개로 코드가 계산한다
# =============================================================================

def test_criteria_reproduce_every_ai4i_label_for_hdf_pwf_osf():
    """HDF·PWF·OSF 는 AI4I 의 생성 조건이다. 1만 행 전부에서 라벨과 같아야 한다."""
    df = pd.read_csv(DATA / "source" / "ai4i2020.csv")
    df.columns = ["udi", "pid", "grade", "air", "proc", "rpm", "torque", "wear",
                  "mf", "TWF", "HDF", "PWF", "OSF", "RNF"]
    mismatches = {"HDF": 0, "PWF": 0, "OSF": 0}
    for row in df.itertuples(index=False):
        snapshot = SensorSnapshot(
            air_temperature_k=row.air, process_temperature_k=row.proc,
            rotational_speed_rpm=row.rpm, torque_nm=row.torque, tool_wear_min=row.wear,
            temp_diff_k=row.proc - row.air, power_w=row.torque * row.rpm * 2 * 3.141592653589793 / 60)
        met = {c.failure_type: c.met for c in check_criteria(snapshot, row.grade)}
        for t in mismatches:
            mismatches[t] += met[t] != bool(getattr(row, t))
    assert mismatches == {"HDF": 0, "PWF": 0, "OSF": 0}


@pytest.mark.parametrize("wear, expected", [(199, False), (200, True), (240, True), (253, True)])
def test_twf_criterion_starts_at_the_risk_window(wear, expected):
    snapshot = SensorSnapshot(air_temperature_k=300, process_temperature_k=310,
                              rotational_speed_rpm=1500, torque_nm=40, tool_wear_min=wear,
                              temp_diff_k=10, power_w=6283)
    twf = next(c for c in check_criteria(snapshot, "L") if c.failure_type == "TWF")
    assert twf.met is expected


def test_a_prediction_is_not_a_criterion():
    """S08: 모델은 OSF 를 예측했지만 판정 기준이 성립한 것은 TWF 다."""
    card = _card("S08")
    assert card.prediction.predicted_failure_type == "OSF"
    assert met_types(check_criteria(card.sensor_snapshot, card.quality_grade)) == {"TWF"}


# =============================================================================
# 매뉴얼 근거 — 녹화된 실제 임베딩으로 돈다. 키가 없어도 순위가 진짜다
# =============================================================================

def test_every_chunk_and_card_query_is_recorded():
    """녹화가 빠진 문장이 하나라도 있으면 앱이 그 카드에서 503 을 낸다."""
    recorded = recorded_embeddings()
    recorded.embed_documents([c.page_content for c in load_chunks()])
    for card in load_cards().values():
        for _, text in card_queries(card):
            assert len(recorded.embed_query(text)) == 256


def test_an_unrecorded_sentence_stops_instead_of_faking():
    with pytest.raises(NotRecorded):
        recorded_embeddings().embed_query("녹화하지 않은 새 질문입니다")


def test_type_sections_are_found_for_almost_every_query():
    """126개 질의 중 125개. 놓친 하나(EVT-2025-0044 HDF)는 근거 신호가 예측 유형의 것뿐이라서다."""
    missed, total, sop_missed = [], 0, 0
    for card in load_cards().values():
        _, _, per = find_evidence(card)
        for t in card.prediction.candidates:
            total += 1
            if not any(c.startswith(SECTION[t]) for c in per[f"{t} 판정·점검"]):
                missed.append((card.event_id, t))
        sop_missed += not any(c.startswith("SOP-EA-01 4") for c in per["확신도 대응"])
    assert total == 126
    assert missed == [("EVT-2025-0044", "HDF")]
    assert sop_missed == 0


def test_each_citation_appears_once():
    """질의끼리 같은 절을 찾는 카드가 있어야 이 검사가 무엇이든 본다."""
    overlapping = 0
    for card in load_cards().values():
        _, evidence, per = find_evidence(card)
        ids = [e.evidence_id for e in evidence]
        assert len(ids) == len(set(ids)), card.event_id
        found = [c for cites in per.values() for c in cites]
        overlapping += len(found) > len(set(found))
    assert overlapping >= 1, "질의끼리 겹치는 카드가 없으면 이 검사는 아무것도 확인하지 않는다"


def test_search_index_holds_only_manuals():
    for line in (DATA / "index" / "manual_chunks.jsonl").read_text(encoding="utf-8").splitlines():
        meta = json.loads(line)["metadata"]
        assert meta["provenance"] == "synthetic_manual"
        assert meta["doc_id"] in {"MC01-MM", "SOP-EA-01", "ML-GUIDE-01"}


def test_pdf_chunks_lose_the_section_number():
    """PDF 로 적재하면 절 번호 인용이 사라진다. 그래서 md 가 정본이다(Notebook 02)."""
    pdf = [json.loads(line)["metadata"]
           for line in (DATA / "index" / "manual_chunks_pdf.jsonl").read_text(encoding="utf-8").splitlines()]
    assert pdf and all(" p." in m["citation"] for m in pdf)


# =============================================================================
# 정비 이력 — 이벤트 시각보다 뒤의 기록은 절대 돌려주지 않는다
# =============================================================================

def test_history_never_returns_records_after_the_event(store):
    with closing(sqlite3.connect(DATA / "history" / "history.sqlite")) as db:
        for s in scenarios():
            card = EventCard.model_validate(s["card"])
            for item in store.gather(card.sensor_snapshot, card.quality_grade,
                                     card.prediction.predicted_failure_type, card.detected_at):
                occurred = db.execute("SELECT occurred_at FROM maintenance_record WHERE record_id = ?",
                                      (item.evidence_id,)).fetchone()[0]
                assert occurred < card.detected_at, (card.event_id, item.evidence_id)


def test_history_gathers_every_kind_the_sop_asks_for(store):
    card = _card("S01")
    reasons = {i.reason.split("(")[0] for i in store.gather(
        card.sensor_snapshot, card.quality_grade, card.prediction.predicted_failure_type, card.detected_at)}
    assert {"같은 유형", "센서 값이 가까운 기록", "같은 예측", "마지막 공구 교체"} <= reasons


def test_the_history_db_refuses_writes():
    """쓰기 시도는 DB 헤더 쓰기로 한다. 이 저장소는 코드에 데이터 변경 SQL 문자열이 있으면
    막는다(tests/test_security_invariants.py). 헤더 쓰기도 읽기 전용 연결에서는 거부된다."""
    from task10_maintenance.tools import history
    with pytest.raises(sqlite3.OperationalError, match="readonly"):
        with closing(history()._connect()) as db:
            db.execute("PRAGMA user_version = 7")


# =============================================================================
# 이력 Tool 과 Agent
# =============================================================================

def test_quality_grade_is_an_enum_in_the_schema():
    schema = criteria_tool.args_schema.model_json_schema()
    assert schema["properties"]["quality_grade"]["enum"] == ["L", "M", "H"]


def test_a_malformed_time_is_blocked():
    """조회 시점은 문자열 비교다. 형식이 틀리면 조용히 틀리므로 막는다."""
    with pytest.raises(ValueError, match="ISO"):
        same_type_history.invoke({"failure_type": "HDF", "before": "8월 22일"})


@pytest.mark.parametrize("sid", [f"S{n:02d}" for n in range(1, 11)])
def test_fixture_lookup_respects_the_dependency_and_misses_nothing(sid):
    card = _card(sid)
    result = asyncio.run(lookup(card))
    assert result.dependency_respected
    assert result.missing_history_types == []
    assert not result.run.budget_exhausted
    assert {c.failure_type for c in result.criteria if c.met} == met_types(
        check_criteria(card.sensor_snapshot, card.quality_grade))


def test_a_skipped_type_is_reported():
    """모델이 기준 성립 유형(TWF)을 빠뜨리면 기록에서 그것을 찾아낸다. live 에서 실제로 일어났다."""
    card = _card("S08")
    first, second, done = fixture_plan(card)
    second = AIMessage(content="", tool_calls=[c for c in second.tool_calls if c["args"]["failure_type"] != "TWF"])
    agent = build_agent(ScriptedToolModel(messages=iter([first, second, done])), LOCAL_TOOLS, step_budget=STEP_BUDGET)
    result = read_run(card, run_agent(agent, question_for(card), step_budget=STEP_BUDGET))
    assert result.missing_history_types == ["TWF"]


def test_an_mcp_error_text_is_not_counted_as_success():
    """MCP 는 서버 쪽 오류를 정상 결과 글자로 돌려준다. 상태만 보면 성공으로 센다."""
    card = _card("S08")
    run = AgentRun(answer="", observations=[Observation(
        tool="same_type_history", arguments={"failure_type": "TWF", "before": card.detected_at},
        result="Error executing tool same_type_history: 1 validation error", ok=True)])
    assert read_run(card, run).history_types == []


def test_history_calls_in_the_first_turn_break_the_dependency():
    card = _card("S08")
    messages = [AIMessage(content="", tool_calls=[
        {"name": "check_criteria", "args": {}, "id": "a"},
        {"name": "same_type_history", "args": {"failure_type": "OSF", "before": card.detected_at}, "id": "b"}]),
        ToolMessage(content="{}", tool_call_id="a"), ToolMessage(content="{}", tool_call_id="b")]
    assert read_run(card, AgentRun(answer="", messages=messages)).dependency_respected is False


@pytest.mark.parametrize("budget, exhausted", [(STEP_BUDGET, False), (2, True)])
def test_the_step_budget_is_reachable(budget, exhausted):
    """정상 경로는 Tool 턴 2번이다. 상한 2 면 소진되어야 한다(도달 가능한 상한)."""
    assert asyncio.run(lookup(_card("S07"), step_budget=budget)).run.budget_exhausted is exhausted


def test_the_mcp_server_opens_exactly_the_read_only_tools():
    """MCP 로 나가는 표면을 **실제로 띄워서** 센다."""
    tools = asyncio.run(mcp_tools({"history": stdio_server(MCP_SERVER_MODULE)}))
    assert {t.name for t in tools} == set(READ_ONLY_TOOLS)
    assert set(mcp_server._tool_manager._tools) == set(READ_ONLY_TOOLS)


def test_local_and_mcp_paths_give_the_same_answer(monkeypatch):
    card = _card("S08")
    local = asyncio.run(lookup(card))
    monkeypatch.setenv("MCP_MODE", "on")
    remote = asyncio.run(lookup(card))
    assert [h.evidence_id for h in remote.history] == [h.evidence_id for h in local.history]
    assert remote.history_types == local.history_types


# =============================================================================
# 경로 — SOP-EA-01 규칙. LLM 에게 묻지 않는다
# =============================================================================

@pytest.mark.parametrize("sid", [f"S{n:02d}" for n in range(1, 11)])
def test_each_scenario_takes_the_route_the_sop_says(sid, store):
    s = _scenario(sid)
    card = EventCard.model_validate(s["card"])
    repairs = [CompletedRepair.model_validate(r) for r in s["completed_repairs"]]
    criteria = check_criteria(card.sensor_snapshot, card.quality_grade)
    evidence = store.gather(card.sensor_snapshot, card.quality_grade,
                            card.prediction.predicted_failure_type, card.detected_at)
    assert decide_route(card, criteria, evidence, repairs) == (s["expected_route"], s["expected_reasons"])


def test_no_evidence_is_escalated():
    """ESC-4 는 데이터로 만들 수 없어 근거를 비워 확인한다."""
    card = _card("S01")
    criteria = check_criteria(card.sensor_snapshot, card.quality_grade)
    assert decide_route(card, criteria, []) == ("escalation", ["ESC-4"])


def test_back_to_back_alarms_are_not_a_recurrence(store):
    """조치 전에 연달아 온 경보는 재발이 아니다. 조치 완료 뒤 24시간 안이어야 한다."""
    card = _card("S10")
    criteria = check_criteria(card.sensor_snapshot, card.quality_grade)
    evidence = store.gather(card.sensor_snapshot, card.quality_grade, "HDF", card.detected_at)
    assert decide_route(card, criteria, evidence, [])[0] == "grounded_draft"
    at = datetime.fromisoformat(card.detected_at)
    stale = CompletedRepair(event_id="X", failure_type="HDF", completed_at=(at - timedelta(hours=25)).isoformat())
    other = CompletedRepair(event_id="Y", failure_type="PWF", completed_at=(at - timedelta(hours=2)).isoformat())
    assert decide_route(card, criteria, evidence, [stale, other])[0] == "grounded_draft"


# =============================================================================
# 초안 검사
# =============================================================================

def _response(**change) -> AgentResponse:
    evidence = [
        EvidenceItem(evidence_id="MC01-MM 4.2.3", kind="manual", reason="판정 기준",
                     excerpt="흡기 필터(PN-FL-3120)의 압력차 표시를 확인합니다."),
        EvidenceItem(evidence_id="MR-0097", kind="history", reason="같은 유형(HDF) 최근 수리 기록",
                     excerpt="HDF | 냉각팬 모듈 교체 | 교체 부품: PN-CF-3105"),
    ]
    base = dict(
        event_id="EVT-2025-0034", route="grounded_draft", criteria_check=[], evidence=evidence,
        escalation_reasons=[],
        cause_candidates=[CauseCandidate(rank=1, failure_type="HDF", rationale="흡기 필터 막힘 가능성",
                                         evidence_ids=["MC01-MM 4.2.3", "MR-0097"])],
        inspection_steps=[InspectionStep(order=1, instruction="필터 압력차를 확인한다",
                                         evidence_ids=["MC01-MM 4.2.3"])],
        parts_to_prepare=["PN-FL-3120"], drafted_by="fixture_script")
    base.update(change)
    return AgentResponse(**base)


def test_a_well_formed_draft_passes():
    assert validate_response(_response()) == []


@pytest.mark.parametrize("change, fragment", [
    (dict(cause_candidates=[CauseCandidate(rank=1, failure_type="HDF", rationale="필터 막힘",
                                           evidence_ids=["MR-9999"])]), "근거 목록에 없는"),
    (dict(cause_candidates=[CauseCandidate(rank=1, failure_type="HDF", rationale="필터 막힘으로 확정",
                                           evidence_ids=["MR-0097"])]), "단정"),
    (dict(route="inspect_only"), "원인 후보를 비워야"),
    (dict(inspection_steps=[]), "하나 이상"),
    (dict(route="escalation", escalation_reasons=[]), "ESC 조건 코드"),
    (dict(parts_to_prepare=["PN-BR-5510"]), "근거에 없는 부품"),
    (dict(inspection_steps=[InspectionStep(order=2, instruction="확인", evidence_ids=["MR-0097"])]), "1부터"),
])
def test_each_contract_breach_is_caught(change, fragment):
    errors = validate_response(_response(**change))
    assert any(fragment in e for e in errors), errors


def test_parts_come_only_from_manuals_and_same_type_repairs():
    evidence = [
        EvidenceItem(evidence_id="MC01-MM 5.3", kind="manual", reason="m", excerpt="필터(PN-FL-3120)"),
        EvidenceItem(evidence_id="MR-1", kind="history", reason="같은 유형(HDF) 최근 수리 기록",
                     excerpt="HDF | 교체 부품: PN-CF-3105"),
        EvidenceItem(evidence_id="MR-2", kind="history", reason="센서 값이 가까운 기록(거리 0.3)",
                     excerpt="PWF | 교체 부품: PN-IV-4410"),
    ]
    assert parts_to_prepare(evidence, {"HDF"}) == ["PN-FL-3120", "PN-CF-3105"]


def test_only_approve_and_escalate_become_reports():
    card = _card("EVT-2025-0034")
    for decision in ("revise", "reject"):
        with pytest.raises(NotAReport):
            build_report(card, _response(), ReviewDecision(decision=decision, reviewer_role="정비 기술자"))
    report = build_report(card, _response(),
                          ReviewDecision(decision="escalate", reviewer_role="정비 기술자", note="냉각수 냄새"))
    assert report.escalation == ["검토자 escalation: 냉각수 냄새"]
    assert "MR-0097" in render_markdown(report)


# =============================================================================
# 그래프 — 병렬 수집, 다시 쓰기, 사람 앞에서 멈춤
# =============================================================================

def _until_review(card: EventCard, repairs=(), thread="t"):
    """사람 검토 앞까지 돌리고 멈춘 상태를 돌려준다."""
    async def flow():
        graph = build_case_graph(InMemorySaver())
        config = {"configurable": {"thread_id": thread}}
        await graph.ainvoke(start_input(card, list(repairs)), config)
        return (await graph.aget_state(config)).values
    return asyncio.run(flow())


def _merged(card: EventCard) -> dict:
    """두 담당과 merge 만 돌린 결과. 초안 대역을 만들 때 쓴다."""
    state = {"card": card}
    state.update(review_module.collect_manual(state))
    state.update(asyncio.run(review_module.collect_history(state)))
    state.update(review_module.merge(state))
    return state


def _writer(monkeypatch, replies):
    """초안 대역을 한 요청 동안 공유한다. 첫 번째와 두 번째 초안을 다르게 줄 수 있다."""
    model = GenericFakeChatModel(messages=iter(replies))
    monkeypatch.setattr(drafting, "chat_model", lambda _fixture=None: model)


def _good_and_bad(card: EventCard) -> tuple[str, str]:
    state = _merged(card)
    good = json.loads(drafting.fixture_draft(card, state["criteria"], state["evidence"]))
    bad = json.loads(json.dumps(good))
    bad["inspection_steps"][0]["evidence_ids"] = ["MC01-MM 4.2.5"]          # 없는 절
    return json.dumps(bad, ensure_ascii=False), json.dumps(good, ensure_ascii=False)


@pytest.mark.parametrize("sid", [f"S{n:02d}" for n in range(1, 11)])
def test_each_scenario_stops_for_review_on_its_route(sid):
    s = _scenario(sid)
    values = _until_review(EventCard.model_validate(s["card"]),
                           [CompletedRepair.model_validate(r) for r in s["completed_repairs"]], sid)
    r = values["response"]
    assert r.route == s["expected_route"]
    assert values["errors"] == []
    if r.route == "escalation":
        assert r.escalation_reasons == s["expected_reasons"]
        assert r.cause_candidates == [] and r.drafted_by == "code"
    elif r.route == "inspect_only":
        assert r.cause_candidates == [] and r.drafted_by == "code"
        assert any("SOP-EA-01 8" in st.evidence_ids for st in r.inspection_steps)
    else:
        assert r.cause_candidates and r.inspection_steps and r.drafted_by == "fixture_script"
        assert r.parts_to_prepare


def test_an_invalid_first_draft_is_rewritten_once(monkeypatch):
    card = _card("EVT-2025-0034")
    bad, good = _good_and_bad(card)
    _writer(monkeypatch, [bad, good])
    values = _until_review(card)
    assert [t for t in values["trace"] if t.startswith(("draft", "validate"))] == \
        ["draft#1", "validate:오류 1", "draft#2", "validate:통과"]
    assert values["errors"] == []


def test_the_retry_is_bounded(monkeypatch):
    """두 번 다 틀리면 오류를 단 채 사람에게 간다. 무한히 다시 쓰지 않는다."""
    card = _card("EVT-2025-0034")
    bad, _ = _good_and_bad(card)
    _writer(monkeypatch, cycle([bad]))
    values = _until_review(card)
    assert values["attempts"] == MAX_ATTEMPTS
    assert values["errors"] and "근거 목록에 없는" in values["errors"][0]


def test_a_malformed_draft_is_treated_as_a_failed_check(monkeypatch):
    card = _card("EVT-2025-0034")
    _, good = _good_and_bad(card)
    _writer(monkeypatch, ["원인은 아마 필터입니다.", good])
    values = _until_review(card)
    assert "draft#1(형식 오류)" in values["trace"]
    assert values["errors"] == []


def test_history_the_agent_skipped_is_filled_by_code(monkeypatch):
    """live 에서 실제 모델이 필요한 유형을 빠뜨렸다. 이력 담당은 코드로 채운다."""
    real_lookup = review_module.lookup

    async def skipping(card, **kwargs):
        result = await real_lookup(card, **kwargs)
        result.history = [h for h in result.history if not h.reason.startswith("같은 유형(TWF)")]
        result.history_types = [t for t in result.history_types if t != "TWF"]
        return result

    monkeypatch.setattr(review_module, "lookup", skipping)
    values = _until_review(_card("S08"))
    assert values["filled_history_types"] == ["TWF"]
    assert any(e.reason.startswith("같은 유형(TWF)") for e in values["response"].evidence)


def test_both_collectors_run_before_merge():
    trace = _until_review(_card("EVT-2025-0002"))["trace"]
    merge_at = trace.index("merge")
    assert "collect_manual" in trace[:merge_at]
    assert any(t.startswith("collect_history") for t in trace[:merge_at])


# =============================================================================
# 평가 — 경로 분포와 시스템 재현율
# =============================================================================

def test_route_distribution_and_system_recall():
    """규칙이 바뀌면 이 숫자가 바뀐다(Notebook 12 해설과 같은 숫자)."""
    result = evaluate("recorded")
    assert result["scenarios_passed"] == 10
    assert {r["route"]: r["failures"] + r["false_alarms"] for r in result["routes"]} == \
        {"grounded_draft": 75, "escalation": 17, "inspect_only": 19}
    inspect = next(r for r in result["routes"] if r["route"] == "inspect_only")
    assert inspect["failures"] == 0, "고장인데 오탐 점검으로 보낸 카드가 생겼다"
    assert result["system"] == {"actual_failures": 99, "alarmed": 74, "missed_by_ml": 25,
                                "system_recall": 0.747,
                                "missed_types": {"TWF": 10, "UNKNOWN": 2, "OSF": 5, "HDF": 8}}


def test_completed_repairs_change_the_route():
    s10 = _scenario("S10")
    card = EventCard.model_validate(s10["card"])
    repairs = [CompletedRepair.model_validate(r) for r in s10["completed_repairs"]]
    assert route_for(card) == ("grounded_draft", [])
    assert route_for(card, repairs) == ("escalation", ["ESC-5"])


# =============================================================================
# 데이터 경계
# =============================================================================

def test_eventcards_carry_no_answer():
    banned = {"machine_failure", "actual_failure_types", "case", "prediction_correct", "TWF_label"}
    for line in (DATA / "eventcards" / "eventcards.jsonl").read_text(encoding="utf-8").splitlines():
        assert not banned & set(json.loads(line))
    for line in (DATA / "eventcards" / "scenarios.jsonl").read_text(encoding="utf-8").splitlines():
        assert set(json.loads(line)) == {"scenario_id", "card", "completed_repairs"}


# =============================================================================
# 앱
# =============================================================================

@pytest.fixture
def client():
    return TestClient(create_app())


def _start(client, event_id, repairs=()):
    body = client.post("/cases", json={"event_id": event_id, "completed_repairs": list(repairs)}).json()
    assert body["status"] == "awaiting_review"
    return body


def _decide(client, case_id, decision, note=""):
    return client.post(f"/cases/{case_id}/decision", json={"decision": decision, "note": note, **ENGINEER})


def test_approve_makes_a_report(client):
    case = _start(client, "EVT-2025-0034")
    assert case["packet"]["route"] == "grounded_draft"
    assert [q["label"] for q in case["queries"]][-1] == "확신도 대응"
    assert [c["tool"] for c in case["tool_calls"]][0] == "check_criteria"
    body = _decide(client, case["case_id"], "approve").json()
    assert body["status"] == "reported"
    assert body["report"]["review"]["decision"] == "approve"
    assert body["report_markdown"].startswith("# 정비 보고서 — EVT-2025-0034")
    assert body["executed_actions"] == []


def test_escalate_keeps_the_reviewer_reason(client):
    case = _start(client, "EVT-2025-0106")
    body = _decide(client, case["case_id"], "escalate", "엔지니어 확인 필요").json()
    assert body["report"]["escalation"] == ["ESC-3", "검토자 escalation: 엔지니어 확인 필요"]


def test_reject_closes_without_a_report(client):
    case = _start(client, "EVT-2025-0038")
    body = _decide(client, case["case_id"], "reject", "오탐").json()
    assert body["status"] == "rejected" and body["report"] is None


def test_a_completed_repair_sent_with_the_case_escalates(client):
    s10 = _scenario("S10")
    case = _start(client, s10["event_id"], s10["completed_repairs"])
    assert case["packet"]["escalation_reasons"] == ["ESC-5"]


def test_revise_goes_back_to_the_draft_and_asks_again(client):
    case = _start(client, "EVT-2025-0034")
    body = _decide(client, case["case_id"], "revise", "압력차 수치를 넣어 주세요").json()
    assert body["status"] == "awaiting_review"
    assert body["packet"]["revisions"] == 1
    assert body["trace"][-3:] == ["review:revise", "draft#1", "validate:통과"]


def test_revisions_are_bounded(client):
    case = _start(client, "EVT-2025-0034")
    for _ in range(MAX_REVISIONS):
        assert _decide(client, case["case_id"], "revise").status_code == 200
    response = _decide(client, case["case_id"], "revise")
    assert response.status_code == 422
    assert "revise" not in response.json()["detail"]["message"].split("가능한 결정:")[1]


def _bad_drafts(monkeypatch):
    """두 번 다 없는 절을 인용하는 초안. 검사를 통과하지 못한 채 검토로 온다."""
    bad, _ = _good_and_bad(_card("EVT-2025-0034"))
    model = GenericFakeChatModel(messages=cycle([bad]))
    monkeypatch.setattr(drafting, "chat_model", lambda _fixture=None: model)


def test_a_draft_with_errors_cannot_be_approved(client, monkeypatch):
    _bad_drafts(monkeypatch)
    case = _start(client, "EVT-2025-0034")
    assert case["packet"]["validation_errors"]
    assert "approve" not in case["packet"]["allowed_decisions"]
    response = _decide(client, case["case_id"], "approve")
    assert response.status_code == 422
    assert response.json()["detail"]["validation_errors"]
    assert _decide(client, case["case_id"], "escalate").json()["status"] == "reported"


def test_the_graph_asks_again_instead_of_getting_stuck(monkeypatch):
    """앱을 거치지 않고 그래프에 바로 잘못된 결정을 넣어도 건이 굳지 않는다."""
    _bad_drafts(monkeypatch)

    async def flow():
        graph = build_case_graph(InMemorySaver())
        config = {"configurable": {"thread_id": "direct"}}
        await graph.ainvoke(start_input(_card("EVT-2025-0034"), []), config)
        again = await graph.ainvoke(Command(resume={"decision": "approve", **ENGINEER}), config)
        assert "할 수 없습니다" in again["__interrupt__"][0].value["message"]
        done = await graph.ainvoke(Command(resume={"decision": "escalate", **ENGINEER}), config)
        return done["status"]

    assert asyncio.run(flow()) == "reported"


def test_the_same_decision_twice_is_409(client):
    case = _start(client, "EVT-2025-0034")
    assert _decide(client, case["case_id"], "approve").status_code == 200
    assert _decide(client, case["case_id"], "approve").status_code == 409


@pytest.mark.parametrize("payload, status", [({"event_id": "EVT-9999-0000"}, 404), ({}, 422)])
def test_bad_requests_say_what_is_wrong(client, payload, status):
    assert client.post("/cases", json=payload).status_code == status


def test_unknown_case_is_404(client):
    assert client.get("/cases/case-none").status_code == 404
    assert _decide(client, "case-none", "approve").status_code == 404


def test_an_unrecorded_card_is_503_with_the_fix(client):
    card = json.loads((DATA / "eventcards" / "eventcards.jsonl").read_text(encoding="utf-8").splitlines()[0])
    card["prediction"]["top_signals"][0]["feature"] = "air_temperature_k"
    card["prediction"]["top_signals"][1]["feature"] = "quality_grade"
    response = client.post("/cases", json={"card": card})
    assert response.status_code == 503
    assert "APP_MODE=live" in response.json()["message"]


def test_a_paused_case_survives_a_restart(monkeypatch, tmp_path):
    """파일 저장소는 비동기 연결이라 연 이벤트 루프에 묶인다. `with TestClient` 로 클라이언트
    하나의 요청들이 한 루프에서 돌게 한다(uvicorn 처럼)."""
    monkeypatch.setenv("THREAD_DB", str(tmp_path / "threads.sqlite"))
    with TestClient(create_app()) as first:
        case = _start(first, "EVT-2025-0106")
        assert case["thread_durability"] == "file"

    reset_thread_store()                 # 재시작을 흉내 낸다: 저장소와 그래프를 버리고 새로 연다
    app_module.reset_graph()
    with TestClient(create_app()) as second:
        assert second.get(f"/cases/{case['case_id']}").json()["status"] == "awaiting_review"
        assert _decide(second, case["case_id"], "escalate").json()["status"] == "reported"


def test_cards_list_marks_the_scenarios(client):
    marked = client.get("/cards", params={"scenarios_only": True}).json()
    assert sorted(c["scenario_id"] for c in marked) == [f"S{n:02d}" for n in range(1, 11)]
    assert next(c for c in marked if c["scenario_id"] == "S10")["completed_repairs"]


def test_evaluate_endpoint(client):
    body = client.get("/evaluate").json()
    assert body["scenarios_passed"] == 10
    assert body["system"]["system_recall"] == 0.747


def test_diagnostics_never_returns_a_key(client, monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-should-not-leak-0000000000")
    body = client.get("/diagnostics")
    assert body.status_code == 200
    assert "sk-test" not in body.text


# =============================================================================
# Postgres (선택) — DATABASE_URL 로 닿고 적재가 되어 있을 때만 돈다
# =============================================================================

def _postgres_ready() -> str | None:
    """돌 수 없으면 이유를, 돌 수 있으면 None 을 돌려준다."""
    import os

    if not os.getenv("DATABASE_URL", "").strip():
        return "DATABASE_URL 이 없다. docker compose up -d db 와 적재 스크립트 두 개를 돌리면 함께 돈다."
    from task10_maintenance import postgres
    try:
        with closing(postgres.connect()) as db:
            db.execute("SELECT count(*) FROM maintenance_record").fetchone()
            db.execute("SELECT count(*) FROM langchain_pg_embedding").fetchone()
    except Exception as error:   # noqa: BLE001 - 어떤 이유든 이 환경에서는 건너뛴다
        return f"Postgres 에 닿지 않거나 적재 전이다: {type(error).__name__}"
    return None


needs_postgres = pytest.mark.skipif(_postgres_ready() is not None, reason=str(_postgres_ready()))


@pytest.fixture
def on_postgres(monkeypatch):
    from task10_maintenance.evaluation import evaluate
    from task10_maintenance.evidence import hybrid
    from task10_maintenance.history import _store

    monkeypatch.setenv("VECTOR_BACKEND", "pgvector")
    monkeypatch.setenv("HISTORY_BACKEND", "postgres")
    for cached in (hybrid, _store, evaluate):
        cached.cache_clear()
    yield
    for cached in (hybrid, _store, evaluate):
        cached.cache_clear()


@needs_postgres
def test_postgres_history_gives_the_same_records_as_sqlite(store, on_postgres):
    from task10_maintenance.history import history_store
    remote = history_store()
    assert remote.backend == "postgres"
    for s in scenarios():
        card = EventCard.model_validate(s["card"])
        args = (card.sensor_snapshot, card.quality_grade, card.prediction.predicted_failure_type, card.detected_at)
        assert [e.evidence_id for e in remote.gather(*args)] == [e.evidence_id for e in store.gather(*args)], card.event_id


@needs_postgres
def test_the_postgres_history_session_refuses_writes(on_postgres):
    """쓰기 시도는 시퀀스 만들기로 한다(데이터 변경 SQL 문자열은 이 저장소가 막는다)."""
    import psycopg

    from task10_maintenance import postgres
    with pytest.raises(psycopg.errors.ReadOnlySqlTransaction):
        with closing(postgres.connect()) as db:
            db.execute("CREATE SEQUENCE task10_probe")


@needs_postgres
def test_pgvector_finds_the_same_sections_as_faiss(on_postgres, monkeypatch):
    """같은 녹화 임베딩이다. 절의 집합은 같아야 한다. 순서는 거리 함수(L2·코사인) 차이로 바뀔 수 있다."""
    remote = {s["event_id"]: {e.evidence_id for e in find_evidence(EventCard.model_validate(s["card"]))[1]}
              for s in scenarios()}
    monkeypatch.setenv("VECTOR_BACKEND", "faiss")
    local = {s["event_id"]: {e.evidence_id for e in find_evidence(EventCard.model_validate(s["card"]))[1]}
             for s in scenarios()}
    assert remote == local


@needs_postgres
def test_the_app_runs_end_to_end_on_postgres(on_postgres):
    client = TestClient(create_app())
    diagnostics = client.get("/diagnostics").json()
    assert (diagnostics["vector_backend"], diagnostics["history_backend"]) == ("pgvector", "postgres")
    case = _start(client, "EVT-2025-0034")
    assert _decide(client, case["case_id"], "approve").json()["status"] == "reported"
    assert client.get("/evaluate").json()["system"]["system_recall"] == 0.747
