"""사람이 검토한 초안을 정비 보고서로 만든다(SOP-EA-01 7장).

검토 결과에 따라 보고서가 되는지가 갈린다.

    approve   보고서가 된다
    escalate  보고서가 되되 escalation 항목에 검토자의 사유가 붙는다
    revise    보고서가 아니다. 초안을 고쳐 다시 검사·검토한다
    reject    보고서가 아니다. 이 이벤트의 처리를 끝낸다
"""
from __future__ import annotations

from task10_maintenance.domain import (
    AgentResponse,
    EventCard,
    MaintenanceReport,
    ReviewDecision,
)
from task10_maintenance.criteria import describe


class NotAReport(ValueError):
    """검토 결과가 보고서를 만들 수 없는 결정이다."""


def build_report(card: EventCard, response: AgentResponse,
                 review: ReviewDecision) -> MaintenanceReport:
    if review.decision in ("revise", "reject"):
        raise NotAReport(f"검토 결과가 {review.decision} 이라 보고서를 만들지 않습니다.")
    p = card.prediction
    escalation = list(response.escalation_reasons if response.route == "escalation" else [])
    if review.decision == "escalate":
        escalation.append(f"검토자 escalation: {review.note or '사유 미기재'}")
    return MaintenanceReport(
        event_id=card.event_id,
        equipment_id=card.equipment_id,
        detected_at=card.detected_at,
        prediction=(f"{p.predicted_failure_type} 확률 {p.probabilities[p.predicted_failure_type]:.2f} "
                    f"({p.confidence_level}, {card.severity})"),
        criteria_summary=[describe(c) for c in response.criteria_check],
        route=response.route,
        cause_candidates=response.cause_candidates,
        inspection_steps=response.inspection_steps,
        parts_to_prepare=response.parts_to_prepare,
        result="점검 후 기입",
        escalation=escalation,
        drafted_by=response.drafted_by,
        review=review,
    )


def render_markdown(report: MaintenanceReport) -> str:
    lines = [
        f"# 정비 보고서 — {report.event_id}",
        "",
        f"- 설비: {report.equipment_id} · 감지: {report.detected_at}",
        f"- 예측: {report.prediction}",
        f"- 처리 경로: {report.route}",
        "",
        "## 판정 기준 확인",
        *[f"- {line}" for line in report.criteria_summary],
        "",
        "## 추정 원인 후보",
        *([f"{c.rank}. {c.failure_type} — {c.rationale} [{', '.join(c.evidence_ids)}]"
           for c in report.cause_candidates] or ["- 없음"]),
        "",
        "## 점검·조치",
        *([f"{s.order}. {s.instruction} [{', '.join(s.evidence_ids)}]"
           for s in report.inspection_steps] or ["- 없음"]),
        "",
        f"- 준비 부품: {', '.join(report.parts_to_prepare) or '없음'}",
        f"- 결과: {report.result}",
        f"- escalation: {'; '.join(report.escalation) or '없음'}",
        "",
        f"작성: {report.drafted_by} · 검토: {report.review.reviewer_role} "
        f"({report.review.decision}){' — ' + report.review.note if report.review.note else ''}",
    ]
    return "\n".join(lines) + "\n"
