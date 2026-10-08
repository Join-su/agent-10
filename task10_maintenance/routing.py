"""처리 경로를 정하고, 초안이 계약을 지켰는지 검사한다.

경로는 SOP-EA-01 6장(ESC 코드)과 9장 그대로 정한다. **LLM 에게 묻지 않는다.**
LLM 이 쓰는 것은 원인 후보와 점검 단계의 문장뿐이고, 그 문장은 `validate_response`
를 통과해야 사람 검토로 넘어간다.
"""
from __future__ import annotations

import re
from collections.abc import Sequence
from datetime import datetime, timedelta

from task10_maintenance.domain import (
    AgentResponse,
    CompletedRepair,
    CriterionResult,
    EventCard,
    EvidenceItem,
    Route,
)
from task10_maintenance.criteria import met_types

RECURRENCE_WINDOW = timedelta(hours=24)
PART_NO = re.compile(r"PN-[A-Z]{2}-\d{4}")
# SOP-EA-01 7.2: 정비 엔지니어 확인 전에는 원인을 단정하지 않는다.
ASSERTIVE = ("확정", "확실", "틀림없", "분명히")


def decide_route(card: EventCard, criteria: Sequence[CriterionResult],
                 evidence: Sequence[EvidenceItem],
                 completed_repairs: Sequence[CompletedRepair] = ()) -> tuple[Route, list[str]]:
    """경로와 그 사유(ESC 코드 또는 SOP 절)를 돌려준다.

    ESC-1·ESC-6 은 현장에서만 확인할 수 있으므로 여기서 판단하지 않는다.
    """
    met = met_types(criteria)
    predicted = card.prediction.predicted_failure_type
    reasons: list[str] = []
    if len(card.prediction.candidates) >= 2:
        reasons.append("ESC-2")
    if met and predicted not in met:
        reasons.append("ESC-3")
    if not evidence:
        reasons.append("ESC-4")
    if recurred(card, completed_repairs):
        reasons.append("ESC-5")
    if not met and card.severity == "alarm":
        reasons.append("ESC-7")
    if reasons:
        return "escalation", reasons
    if not met:
        return "inspect_only", ["SOP-EA-01 8"]
    return "grounded_draft", []


def recurred(card: EventCard, completed_repairs: Sequence[CompletedRepair]) -> bool:
    """같은 유형을 조치한 뒤 24시간 안에 다시 왔는가.

    직전 이벤트가 아니라 **끝낸 조치**와 비교한다. 경보가 연달아 오는 것까지 재발로
    세면 실제 데이터에서 111장 중 62장이 escalation 이 되어 초안 경로가 사라진다.
    """
    now = datetime.fromisoformat(card.detected_at)
    predicted = card.prediction.predicted_failure_type
    for repair in completed_repairs:
        done = datetime.fromisoformat(repair.completed_at)
        if repair.failure_type == predicted and timedelta(0) < now - done <= RECURRENCE_WINDOW:
            return True
    return False


def parts_to_prepare(evidence: Sequence[EvidenceItem], failure_types: set[str]) -> list[str]:
    """근거에 나온 부품 번호만 모은다. 근거 밖의 부품을 지어내지 않는다.

    매뉴얼 근거 전부와, 이력 중 같은 유형 수리 기록에서만 뽑는다. 센서가 가까울 뿐
    다른 유형인 기록의 부품까지 넣으면 엉뚱한 부품을 준비하게 된다.
    """
    found: list[str] = []
    for item in evidence:
        relevant = item.kind == "manual" or (
            item.reason.startswith("같은 유형") and any(t in item.excerpt for t in failure_types))
        if relevant:
            for part in PART_NO.findall(item.excerpt):
                if part not in found:
                    found.append(part)
    return found


def validate_response(response: AgentResponse) -> list[str]:
    """계약 위반을 찾는다. 빈 목록이면 사람 검토로 넘길 수 있다."""
    errors: list[str] = []
    known = {e.evidence_id for e in response.evidence}

    for label, items in (("원인 후보", response.cause_candidates),
                         ("점검 단계", response.inspection_steps)):
        for item in items:
            unknown = [i for i in item.evidence_ids if i not in known]
            if unknown:
                errors.append(f"{label}가 근거 목록에 없는 ID 를 인용했습니다: {unknown}")
            text = getattr(item, "rationale", None) or getattr(item, "instruction", "")
            if any(word in text for word in ASSERTIVE):
                errors.append(f"{label}가 원인을 단정합니다: {text[:40]}")

    ranks = [c.rank for c in response.cause_candidates]
    if ranks != list(range(1, len(ranks) + 1)):
        errors.append(f"원인 후보 순위가 1부터 이어지지 않습니다: {ranks}")
    orders = [s.order for s in response.inspection_steps]
    if orders != list(range(1, len(orders) + 1)):
        errors.append(f"점검 단계 번호가 1부터 이어지지 않습니다: {orders}")

    if response.route == "grounded_draft":
        if not response.cause_candidates or not response.inspection_steps:
            errors.append("grounded_draft 에는 원인 후보와 점검 단계가 하나 이상 있어야 합니다")
        if response.escalation_reasons:
            errors.append("grounded_draft 에 escalation 사유가 있습니다")
    elif response.route == "escalation":
        if not any(r.startswith("ESC-") for r in response.escalation_reasons):
            errors.append("escalation 에 ESC 조건 코드가 없습니다")
    elif response.route == "inspect_only" and response.cause_candidates:
        errors.append("inspect_only 는 원인을 주장하지 않습니다. 원인 후보를 비워야 합니다")

    excerpts = " ".join(e.excerpt for e in response.evidence)
    invented = [p for p in response.parts_to_prepare if p not in excerpts]
    if invented:
        errors.append(f"근거에 없는 부품 번호입니다: {invented}")
    return errors
