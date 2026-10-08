"""종단 평가 — Agent 의 경로가 맞았는지, 그리고 **Agent 가 아예 보지 못한 고장**까지 센다.

    대표 사례 S01~S10   기대 경로·사유와 실제 경로가 같은가
    경보 111장 전체      경로별로 실제 고장과 오탐이 몇 장씩인가
    시스템 재현율        운영 기간의 실제 고장 중 Agent 에게 경보로 온 비율

Agent 만 평가하면 ML 이 경보를 내지 않은 고장은 보이지 않는다. 그것은 Agent 가
아무리 잘해도 볼 수 없었던 고장이다. 정답은 평가 전용 파일(`data/eval/`)에만 있고
Agent 에게는 주지 않는다.

경로는 그래프의 decide 노드와 같은 규칙(`routing.py::decide_route`)으로 정한다.
사람 검토와 초안은 경로에 영향을 주지 않으므로 여기서는 돌리지 않는다.
"""
from __future__ import annotations

import json
from collections import Counter
from functools import lru_cache
from pathlib import Path

from task10_maintenance.criteria import check_criteria
from task10_maintenance.domain import CompletedRepair, EventCard
from task10_maintenance.evidence import embedding_source, find_evidence, load_cards
from task10_maintenance.postgres import required_url
from task10_maintenance.routing import decide_route

DATA = Path(__file__).resolve().parent / "data"
ROUTES = ("grounded_draft", "escalation", "inspect_only")


def _jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def scenarios() -> list[dict]:
    """대표 사례. 카드·조치 완료 기록과 기대 경로를 함께 돌려준다."""
    index = {s["scenario_id"]: s for s in json.loads((DATA / "eval" / "scenario_index.json").read_text(encoding="utf-8"))}
    return [{**index[line["scenario_id"]], "card": line["card"], "completed_repairs": line["completed_repairs"]}
            for line in _jsonl(DATA / "eventcards" / "scenarios.jsonl")]


def route_for(card: EventCard, completed_repairs: list[CompletedRepair] | None = None) -> tuple[str, list[str]]:
    """그래프의 decide 노드와 같은 판단. 근거는 매뉴얼 검색 결과로 확인한다(ESC-4)."""
    criteria = check_criteria(card.sensor_snapshot, card.quality_grade)
    _, evidence, _ = find_evidence(card)
    return decide_route(card, criteria, evidence, completed_repairs or [])


@lru_cache(maxsize=2)
def evaluate(source: str | None = None) -> dict:
    """데이터가 바뀌지 않으므로 임베딩 출처·저장소마다 한 번만 잰다."""
    del source   # 캐시 열쇠로만 쓴다. 녹화본과 live, 서로 다른 DB 의 결과를 섞지 않는다
    checked = []
    for s in scenarios():
        card = EventCard.model_validate(s["card"])
        repairs = [CompletedRepair.model_validate(r) for r in s["completed_repairs"]]
        route, reasons = route_for(card, repairs)
        checked.append({"scenario_id": s["scenario_id"], "event_id": card.event_id,
                        "teaching_point": s["teaching_point"],
                        "expected_route": s["expected_route"], "expected_reasons": s["expected_reasons"],
                        "route": route, "reasons": reasons,
                        "passed": (route, reasons) == (s["expected_route"], s["expected_reasons"])})

    truth = {t["event_id"]: t for t in _jsonl(DATA / "eval" / "event_truth.jsonl")}
    table = Counter()
    for card in load_cards().values():
        route, _ = route_for(card)
        table[(route, "failure" if truth[card.event_id]["machine_failure"] else "false_alarm")] += 1
    by_route = [{"route": r, "failures": table[(r, "failure")], "false_alarms": table[(r, "false_alarm")]}
                for r in ROUTES]

    missed = _jsonl(DATA / "eval" / "missed_failures.jsonl")
    caught = sum(row["failures"] for row in by_route)
    total = caught + len(missed)
    return {
        "scenarios": checked,
        "scenarios_passed": sum(c["passed"] for c in checked),
        "routes": by_route,
        "system": {
            "actual_failures": total,
            "alarmed": caught,
            "missed_by_ml": len(missed),
            "system_recall": round(caught / total, 3),
            "missed_types": dict(Counter(t for m in missed for t in m["actual_failure_types"])),
        },
        "note": ("시스템 재현율의 한계는 Agent 가 아니라 ML 경보 기준이 정한다. "
                 "Agent 만 평가하면 경보가 없던 고장이 보이지 않는다."),
    }


def current() -> dict:
    return evaluate(f"{embedding_source()}-{required_url()}")
