"""과제 10 — 제조 설비 이상 대응 지원 Agent.

    uv run uvicorn task10_maintenance.app:app --port 8035 --env-file .env --loop task10_maintenance.loop:selector_loop_factory
    (먼저 DB 를 띄우고 적재한다: docker compose up -d db → scripts/task10/ingest_manuals.py → load_history.py)

ML 이 만든 이상 이벤트 카드(EventCard)를 받아, 매뉴얼과 정비 이력에서 근거를 모으고,
SOP 규칙으로 처리 경로를 정하고, 초안을 쓰고 검사한 뒤 **사람 검토 앞에서 멈춘다.**
사람이 결정하면 보고서를 만든다.

    POST /cases                      이벤트를 받아 검토 앞에서 멈춘다
    GET  /cases/{case_id}            멈춘 건의 상태와 검토 packet
    POST /cases/{case_id}/decision   사람의 결정(approve·revise·escalate·reject)을 넣어 재개한다
    GET  /cards                      고를 수 있는 카드와 대표 사례
    GET  /evaluate                   대표 사례 경로 검사와 시스템 재현율

앞 STEP 이 만든 것을 그대로 쓴다. 매뉴얼 검색은 `shared/rag`, 이력 조회 Agent 와 MCP 는
`shared/tools`, 멈춤·재개 저장소는 `shared/graph` 다. 데이터는 전부 Postgres(pgvector) 하나에 있다.

**이 앱은 설비를 제어하지 않는다.** 보고서까지다.
"""
from __future__ import annotations

from uuid import uuid4

from fastapi import FastAPI, HTTPException, Response
from langgraph.types import Command

from shared.graph import ThreadStoreError, graph_config, thread_store, thread_store_durability
from shared.http_errors import register_unavailable
from shared.rag.embedding import EmbeddingConfigurationError
from shared.rag.llm import ChatConfigurationError
from shared.rag.mode import is_live_mode
from shared.rag.store import database_url
from shared.tools import McpToolsUnavailable
from task10_maintenance import evaluation
from task10_maintenance.domain import CardSummary, CaseRequest, CaseResponse, ReviewDecision
from task10_maintenance.evidence import (
    NAMESPACE,
    PER_QUERY,
    WEIGHTS,
    NotRecorded,
    embedding_source,
    load_cards,
    load_chunks,
)
from task10_maintenance.evidence import manual_collection
from task10_maintenance.lookup import FIXTURE_NOTE, STEP_BUDGET, mcp_enabled, tool_source
from task10_maintenance.postgres import PostgresUnavailable
from task10_maintenance.review import (
    DECISIONS,
    MAX_ATTEMPTS,
    MAX_REVISIONS,
    allowed_decisions,
    build_case_graph,
    start_input,
)
from task10_maintenance.tools import READ_ONLY_TOOLS

_GRAPH = None
_GRAPH_STORE = None


async def _graph():
    """그래프는 저장소마다 한 번 만든다. 저장소(Postgres 연결)는 이벤트 루프마다 하나다."""
    global _GRAPH, _GRAPH_STORE
    store = await thread_store()
    if _GRAPH is None or _GRAPH_STORE is not store:
        _GRAPH, _GRAPH_STORE = build_case_graph(store), store
    return _GRAPH


def reset_graph() -> None:
    """설정을 바꾼 뒤 다시 만들게 한다. Test 용이다."""
    global _GRAPH, _GRAPH_STORE
    _GRAPH = _GRAPH_STORE = None


def mode() -> str:
    return "live" if is_live_mode() else "fixture"


def _not_found(case_id: str) -> HTTPException:
    return HTTPException(status_code=404, detail={
        "code": "case_not_found", "message": f"{case_id} 건을 찾을 수 없습니다."})


def _case(case_id: str, values: dict, interrupts) -> CaseResponse:
    waiting = bool(interrupts)
    return CaseResponse(
        case_id=case_id, mode=mode(),
        status="awaiting_review" if waiting else values.get("status", "unknown"),
        packet=interrupts[0].value if waiting else None,
        queries=values.get("queries", []), tool_calls=values.get("tool_calls", []),
        filled_history_types=values.get("filled_history_types", []),
        report=values.get("report"), report_markdown=values.get("report_markdown"),
        trace=values.get("trace", []), thread_durability=thread_store_durability(),
        executed_actions=[])


def create_app() -> FastAPI:
    app = FastAPI(title="과제 10 — 제조 설비 이상 대응 지원 Agent", version="1.0.0")
    register_unavailable(app, McpToolsUnavailable, ChatConfigurationError, NotRecorded,
                         EmbeddingConfigurationError, ThreadStoreError, PostgresUnavailable, FileNotFoundError,
                         code="case_unavailable")
    cards = load_cards()
    scenarios = {s["event_id"]: s for s in evaluation.scenarios()}

    @app.get("/")
    def root() -> dict[str, str]:
        return {"message": "과제 10 설비 이상 대응 지원 Agent", "health": "GET /health",
                "cards": "GET /cards", "start": "POST /cases", "case": "GET /cases/{case_id}",
                "decide": "POST /cases/{case_id}/decision", "evaluate": "GET /evaluate",
                "diagnostics": "GET /diagnostics", "docs": "/docs"}

    @app.get("/favicon.ico", include_in_schema=False, status_code=204)
    def favicon() -> Response:
        return Response(status_code=204)

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok", "project": "task10", "mode": mode()}

    @app.get("/diagnostics")
    def diagnostics() -> dict[str, object]:
        """설정이 빠져도 200 으로 답한다. 키 값은 돌려주지 않는다. 무엇을 쓰는지만 말한다."""
        report: dict[str, object] = {
            "mode": mode(),
            "embedding_source": embedding_source(),
            "recorded_namespace": NAMESPACE,
            "retrieval": {"kind": "EnsembleRetriever(의미 검색, BM25)", "weights": list(WEIGHTS),
                          "per_query": PER_QUERY},
            "database": "postgres (pgvector)",
            "pgvector_collection": manual_collection(),
            "tool_source": tool_source(),
            "tool_choice": "model" if is_live_mode() else "fixture_script",
            "read_only_tools": list(READ_ONLY_TOOLS),
            "step_budget": STEP_BUDGET,
            "drafted_by": "llm" if is_live_mode() else "fixture_script",
            "max_draft_attempts": MAX_ATTEMPTS,
            "max_revisions": MAX_REVISIONS,
            "decisions": list(DECISIONS),
            "routes": ["grounded_draft", "escalation", "inspect_only"],
            "thread_durability": thread_store_durability(),
            "cards": len(cards),
        }
        try:
            report["chunks"] = len(load_chunks())
        except FileNotFoundError as error:
            report["chunks_error"] = str(error)
        if mcp_enabled():
            from task10_maintenance.lookup import MCP_SERVER_MODULE

            report["mcp_server_module"] = MCP_SERVER_MODULE
        if not database_url():
            report["warning"] = "DATABASE_URL 이 없습니다. DB 를 띄우고 적재하세요: docker compose up -d db"
        if not is_live_mode():
            report["note"] = FIXTURE_NOTE
        return report

    @app.get("/cards")
    def list_cards(scenarios_only: bool = False, limit: int = 200) -> list[CardSummary]:
        chosen = [c for c in cards.values() if not scenarios_only or c.event_id in scenarios]
        return [CardSummary(
            event_id=c.event_id, detected_at=c.detected_at, severity=c.severity,
            predicted_failure_type=c.prediction.predicted_failure_type,
            probability=c.prediction.probabilities[c.prediction.predicted_failure_type],
            confidence_level=c.prediction.confidence_level, candidates=list(c.prediction.candidates),
            scenario_id=scenarios.get(c.event_id, {}).get("scenario_id"),
            teaching_point=scenarios.get(c.event_id, {}).get("teaching_point"),
            completed_repairs=scenarios.get(c.event_id, {}).get("completed_repairs", []))
            for c in chosen[:limit]]

    @app.post("/cases")
    async def start(payload: CaseRequest) -> CaseResponse:
        card = cards.get(payload.event_id) if payload.event_id else payload.card
        if card is None:
            raise HTTPException(status_code=404, detail={
                "code": "event_not_found", "message": f"{payload.event_id} 카드가 없습니다."})
        case_id = f"case-{card.event_id}-{uuid4().hex[:8]}"
        g = await _graph()
        await g.ainvoke(start_input(card, payload.completed_repairs), graph_config(case_id))
        snapshot = await g.aget_state(graph_config(case_id))
        return _case(case_id, snapshot.values, snapshot.interrupts)

    @app.get("/cases/{case_id}")
    async def case(case_id: str) -> CaseResponse:
        snapshot = await (await _graph()).aget_state(graph_config(case_id))
        if not snapshot.created_at:
            raise _not_found(case_id)
        return _case(case_id, snapshot.values, snapshot.interrupts)

    @app.post("/cases/{case_id}/decision")
    async def decide(case_id: str, payload: ReviewDecision) -> CaseResponse:
        g = await _graph()
        snapshot = await g.aget_state(graph_config(case_id))
        if not snapshot.created_at:
            raise _not_found(case_id)
        if not snapshot.interrupts:
            raise HTTPException(status_code=409, detail={
                "code": "not_awaiting_review", "message": f"{case_id} 는 검토를 기다리고 있지 않습니다."})
        allowed = allowed_decisions(snapshot.values)
        if payload.decision not in allowed:
            # 재개하기 전에 막는다. 검사 오류가 있는 초안의 승인 같은 결정은 그래프에 닿지 않는다.
            raise HTTPException(status_code=422, detail={
                "code": "decision_not_allowed",
                "message": f"이 초안에는 {payload.decision} 을 할 수 없습니다. 가능한 결정: {allowed}",
                "validation_errors": snapshot.values.get("errors", [])})
        await g.ainvoke(Command(resume=payload.model_dump()), graph_config(case_id))
        after = await g.aget_state(graph_config(case_id))
        return _case(case_id, after.values, after.interrupts)

    @app.get("/evaluate")
    def evaluate() -> dict:
        return evaluation.current()

    return app


app = create_app()
