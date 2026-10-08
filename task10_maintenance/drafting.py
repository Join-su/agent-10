"""초안 쓰기 — 근거만으로 원인 후보와 점검 절차 초안을 쓴다. **LLM 이 하는 유일한 일이다.**

경로·판정·근거 목록·부품은 코드가 이미 정했다. LLM 은 그 근거 안에서 문장만 쓴다.
쓴 것은 `core.validate_response` 를 통과해야 사람에게 간다.

출력은 `PROMPT | model` 다음에 `PydanticOutputParser` 로 받는다. 모델이
무슨 말을 하든 우리가 쓰는 것은 형식이 맞는 필드뿐이다.

fixture 에서는 근거로 초안을 만드는 **정해진 규칙**이 JSON 을 쓴다(`drafted_by =
fixture_script`). 형식과 검증 흐름은 진짜이고, 문장은 대본이다.
"""
from __future__ import annotations

import json

from langchain_core.output_parsers import PydanticOutputParser
from langchain_core.prompts import ChatPromptTemplate
from pydantic import BaseModel

from shared.rag import chat_model, is_live_mode
from task10_maintenance.domain import (
    CauseCandidate,
    CriterionResult,
    EventCard,
    EvidenceItem,
    InspectionStep,
)
from task10_maintenance.criteria import describe
from task10_maintenance.routing import ASSERTIVE

TYPE_SECTION = {"TWF": "MC01-MM 4.1", "HDF": "MC01-MM 4.2", "PWF": "MC01-MM 4.3", "OSF": "MC01-MM 4.4"}


class DraftOutput(BaseModel):
    cause_candidates: list[CauseCandidate]
    inspection_steps: list[InspectionStep]


PARSER = PydanticOutputParser(pydantic_object=DraftOutput)

PROMPT = ChatPromptTemplate.from_messages([
    ("system",
     "당신은 MC-01 설비 정비 보고서 초안을 쓰는 보조자입니다. 아래 규칙을 지키세요.\n"
     "1. 근거 목록에 있는 ID 만 인용합니다(evidence_ids). 목록에 없는 절 번호나 기록 번호를 만들지 마세요.\n"
     "2. 원인 후보(failure_type)는 판정 기준이 성립한 유형 중에서 고릅니다. rank 는 1부터 차례로 붙입니다.\n"
     "3. 원인은 '추정 원인 후보'입니다. 다음 표현을 쓰지 마세요: {assertive}.\n"
     "4. 점검 단계(inspection_steps)는 매뉴얼 절차를 근거로 짧게 씁니다. order 는 1부터 차례로 붙입니다.\n"
     "5. 한국어로 씁니다.\n\n{format_instructions}"),
    ("human",
     "이벤트: {event}\n\n판정 기준 결과:\n{criteria}\n\n근거 목록:\n{evidence}\n\n{feedback}"),
]).partial(format_instructions=PARSER.get_format_instructions(), assertive=", ".join(ASSERTIVE))


class DraftParseError(ValueError):
    """모델 출력이 형식에 맞지 않는다. 검증 실패와 같게 다룬다."""


def render_inputs(card: EventCard, criteria: list[CriterionResult], evidence: list[EvidenceItem],
                  feedback: list[str]) -> dict[str, str]:
    p = card.prediction
    return {
        "event": (f"{card.event_id} · {card.detected_at} · 예측 {p.predicted_failure_type} "
                  f"확률 {p.probabilities[p.predicted_failure_type]:.2f} ({p.confidence_level}) · "
                  f"품질 등급 {card.quality_grade}"),
        "criteria": "\n".join(f"- {describe(c)}" for c in criteria),
        "evidence": "\n".join(f"- [{e.evidence_id}] ({e.reason}) {e.excerpt[:220]}" for e in evidence),
        "feedback": ("앞선 초안이 검증에서 거부되었습니다. 다음 문제를 고쳐 다시 쓰세요:\n"
                     + "\n".join(f"- {f}" for f in feedback)) if feedback else "",
    }


def fixture_draft(card: EventCard, criteria: list[CriterionResult], evidence: list[EvidenceItem]) -> str:
    """fixture 의 초안. 근거에서 정해진 규칙으로 만든다. **문장은 대본이다.**"""
    ids = {e.evidence_id for e in evidence}
    met = [c for c in criteria if c.met]
    predicted = card.prediction.predicted_failure_type
    met.sort(key=lambda c: c.failure_type != predicted)
    candidates, steps = [], []
    for rank, c in enumerate(met, start=1):
        history = next((e.evidence_id for e in evidence
                        if e.kind == "history" and e.reason.startswith(f"같은 유형({c.failure_type})")), None)
        candidates.append({"rank": rank, "failure_type": c.failure_type,
                           "rationale": f"판정 기준 성립({c.citation}). "
                                        + (f"같은 유형 최근 수리 {history} 의 조치를 참고할 수 있다." if history else ""),
                           "evidence_ids": [c.citation] + ([history] if history else [])})
        for suffix, verb in ((".3", "점검 절차"), (".4", "권장 조치")):
            section = TYPE_SECTION[c.failure_type] + suffix
            if section in ids:
                steps.append({"order": len(steps) + 1, "instruction": f"{section} 의 {verb}를 따른다",
                              "evidence_ids": [section]})
    if any(c.failure_type == "TWF" for c in met):
        last = next((e.evidence_id for e in evidence if e.reason == "마지막 공구 교체"), None)
        if last:
            steps.append({"order": len(steps) + 1, "instruction": "마지막 공구 교체 기록과 현재 마모 시간을 대조한다",
                          "evidence_ids": [last]})
    return json.dumps({"cause_candidates": candidates, "inspection_steps": steps}, ensure_ascii=False)


async def write_draft(card: EventCard, criteria: list[CriterionResult], evidence: list[EvidenceItem],
                      feedback: list[str] | None = None) -> tuple[DraftOutput, str]:
    """초안과 작성 주체(llm / fixture_script)를 돌려준다."""
    model = chat_model(fixture_draft(card, criteria, evidence))
    chain = PROMPT | model
    message = await chain.ainvoke(render_inputs(card, criteria, evidence, feedback or []))
    try:
        draft = PARSER.parse(message.content)
    except Exception as error:   # 형식이 깨진 출력도 검증 실패로 되돌린다
        raise DraftParseError(f"초안 형식이 맞지 않습니다: {type(error).__name__}") from error
    return draft, ("llm" if is_live_mode() else "fixture_script")
