"""이력 Tool — 판정 기준 계산과 정비 이력 조회를 Tool 로 연다.

**스키마를 손으로 적지 않는다.** `@tool` 이 시그니처와 docstring 에서 만든다.
`Literal` 로 적은 인자는 스키마에 허용값 목록(enum)이 되고, 그 밖의 값은 함수에
닿기 전에 막힌다.

의존 관계가 진짜로 있다.

    check_criteria     ┐
    past_false_alarms  ├─ EventCard 만 있으면 부를 수 있다. 함께 불러도 된다
    last_tool_change   ┘
    same_type_history     ← 어느 유형을 찾을지는 check_criteria 결과를 봐야 안다

예측은 OSF 인데 판정 기준은 TWF 가 성립하는 카드(S08)에서, 첫 턴에 예측 유형
이력만 찾고 끝내면 TWF 이력을 놓친다.

전부 **읽기 전용**이다. 이력 DB(Postgres)는 읽기 전용 세션으로 열린다.
결과는 JSON 문자열이다. 안에서 부르든 MCP 로 부르든 같은 모양이어야 한다.
"""
from __future__ import annotations

import json
from datetime import datetime
from typing import Literal

from langchain_core.tools import BaseTool, tool

from task10_maintenance.domain import EvidenceItem, SensorSnapshot
from task10_maintenance.criteria import check_criteria as compute_criteria, met_types
from task10_maintenance.history import HistoryStore, history_store

FailureType = Literal["TWF", "HDF", "PWF", "OSF"]


def history() -> HistoryStore:
    """정비 이력 저장소(Postgres, 읽기 전용 세션)."""
    return history_store()


def _moment(before: str) -> str:
    """조회 시점. ISO 형식이 아니면 막는다. 문자열 비교라 형식이 틀리면 조용히 틀린다."""
    try:
        datetime.fromisoformat(before)
    except ValueError as error:
        raise ValueError(f"before 는 ISO 시각이어야 합니다(예: 2025-08-22T06:30:00+09:00). 받은 값: {before!r}") from error
    return before


def _items(items: list[EvidenceItem]) -> str:
    return json.dumps({"records": [i.model_dump() for i in items],
                       "summary": f"{len(items)}건: " + ", ".join(i.evidence_id for i in items)},
                      ensure_ascii=False)


@tool
def check_criteria(air_temperature_k: float, process_temperature_k: float,
                   rotational_speed_rpm: float, torque_nm: float, tool_wear_min: float,
                   quality_grade: Literal["L", "M", "H"]) -> str:
    """매뉴얼 판정 기준(MC01-MM 부록 A)을 센서 값에 적용한다. 네 유형(TWF·HDF·PWF·OSF) 각각의
    해당 여부, 계산값, 근거 절을 돌려준다. 온도 차와 기계 출력은 이 Tool 이 계산한다."""
    snapshot = SensorSnapshot(
        air_temperature_k=air_temperature_k, process_temperature_k=process_temperature_k,
        rotational_speed_rpm=rotational_speed_rpm, torque_nm=torque_nm, tool_wear_min=tool_wear_min,
        temp_diff_k=round(process_temperature_k - air_temperature_k, 2),
        power_w=round(torque_nm * rotational_speed_rpm * 2 * 3.141592653589793 / 60, 0))
    results = compute_criteria(snapshot, quality_grade)
    met = sorted(met_types(results))
    return json.dumps({"met": met, "results": [r.model_dump() for r in results],
                       "summary": f"기준 성립: {', '.join(met) or '없음'}"}, ensure_ascii=False)


@tool
def same_type_history(failure_type: FailureType, before: str) -> str:
    """정비 이력에서 이 유형으로 수리한 최근 기록 3건을 찾는다. before 시각보다 앞선 기록만 돌려준다.
    before 에는 EventCard 의 detected_at 을 그대로 넣는다."""
    return _items(history().same_type_recent(failure_type, _moment(before)))


@tool
def past_false_alarms(predicted_type: FailureType, before: str) -> str:
    """같은 예측 유형으로 점검했는데 고장이 아니었던 과거 기록(오탐 점검)을 최근 2건 찾는다.
    before 시각보다 앞선 기록만 돌려준다."""
    items = history().past_false_alarms(predicted_type, _moment(before))
    count = history().false_alarm_count(predicted_type, before)
    data = json.loads(_items(items))
    data["total_before"] = count
    data["summary"] = f"과거 {predicted_type} 오탐 점검 {count}건 중 최근 {len(items)}건"
    return json.dumps(data, ensure_ascii=False)


@tool
def last_tool_change(before: str) -> str:
    """마지막으로 공구를 교체한 기록을 찾는다(정기 교체와 공구 교체를 겸한 수리 포함).
    before 시각보다 앞선 기록만 돌려준다."""
    return _items(history().last_tool_change(_moment(before)))


LOCAL_TOOLS: list[BaseTool] = [check_criteria, same_type_history, past_false_alarms, last_tool_change]
READ_ONLY_TOOLS = tuple(t.name for t in LOCAL_TOOLS)
INDEPENDENT = ("check_criteria", "past_false_alarms", "last_tool_change")
DEPENDENT = ("same_type_history",)
