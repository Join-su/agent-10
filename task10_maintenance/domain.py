"""과제 10 학습 자료의 데이터 계약.

Agent 가 받는 입력(EventCard), 찾아볼 과거 기록(MaintenanceRecord), 내놓는 결과
(AgentResponse → 사람 검토 → MaintenanceReport)의 모양을 여기서 한 번만 정한다.
`schemas/*.json` 은 이 파일에서 생성한다.

**EventCard 에는 정답이 없다.** 실제로 고장이었는지, 어떤 유형이었는지는
`data/eval/` 에만 있다. Agent 가 정답을 보고 답하면 평가가 성립하지 않는다.

**판정은 코드가 하고 LLM 은 문장만 쓴다.** AgentResponse 의 필드마다 누가 채우는지
정해 두었다. 코드가 채우는 필드는 fixture 모드에서도 진짜 결과다.
"""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

FailureType = Literal["TWF", "HDF", "PWF", "OSF"]
"""모델이 예측하는 유형. RNF(무작위 고장)는 예측할 수 없으므로 없다."""

HistoryFailureType = Literal["TWF", "HDF", "PWF", "OSF", "RNF", "UNKNOWN"]
"""과거 기록에 남는 유형. 사람이 확인한 결과라 RNF·원인 미상도 있다."""


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class SensorSnapshot(Strict):
    """이벤트 시점의 센서 값. AI4I 2020 의 다섯 값에 파생 값 둘을 더했다."""

    air_temperature_k: float
    process_temperature_k: float
    rotational_speed_rpm: float
    torque_nm: float
    tool_wear_min: float
    temp_diff_k: float = Field(description="공정 온도 - 공기 온도")
    power_w: float = Field(description="토크 × 각속도. 스핀들 기계 출력")


class Signal(Strict):
    """모델이 이 예측을 낸 데 가장 크게 기여한 입력."""

    feature: str
    value: float
    reference: float = Field(description="학습 기간의 평균값")
    contribution: float = Field(description="로지스틱 회귀의 기여도(계수 × 표준화 값)")


class Prediction(Strict):
    model_id: str
    predicted_failure_type: FailureType
    probabilities: dict[FailureType, float]
    thresholds: dict[FailureType, float]
    candidates: list[FailureType] = Field(description="임계값을 넘은 유형 전부. 둘 이상이면 복합 의심")
    confidence_level: Literal["high", "medium", "low"]
    top_signals: list[Signal]


class EventCard(Strict):
    """ML 이 고장 가능성을 감지해 만든 이상 이벤트. **Agent 의 입력이다.**"""

    event_id: str = Field(pattern=r"^EVT-2025-\d{4}$")
    equipment_id: Literal["MC-01"]
    detected_at: str
    severity: Literal["alarm", "warning"]
    product_id: str
    quality_grade: Literal["L", "M", "H"]
    sensor_snapshot: SensorSnapshot
    prediction: Prediction
    data_lineage: dict[str, str]


class PartUsed(Strict):
    part_no: str
    name: str
    qty: int


class PastAlarm(Strict):
    """그 기록이 ML 알람으로 시작됐다면 그때의 예측."""

    predicted_failure_type: FailureType
    probability: float


class MaintenanceRecord(Strict):
    """MC-01 의 과거 정비 기록. 사람이 확인한 결과다."""

    record_id: str = Field(pattern=r"^MR-\d{4}$")
    equipment_id: Literal["MC-01"]
    occurred_at: str
    record_type: Literal["failure_repair", "tool_change", "false_alarm_check"]
    trigger: Literal["ml_alarm", "operator_report", "scheduled"]
    past_alarm: PastAlarm | None
    failure_types: list[HistoryFailureType]
    quality_grade: Literal["L", "M", "H"]
    sensor_snapshot: SensorSnapshot
    symptom: str
    diagnosis: str
    action: str
    parts_replaced: list[PartUsed]
    downtime_min: int
    outcome: str
    manual_refs: list[str]
    technician: str
    source: dict[str, str]
    provenance: Literal["synthetic_from_ai4i2020"]


class EventTruth(Strict):
    """평가 전용. Agent 에게 주지 않는다."""

    event_id: str
    machine_failure: bool
    actual_failure_types: list[HistoryFailureType]
    prediction_correct: bool
    case: Literal["correct", "type_mismatch", "false_alarm", "label_inconsistent"]


# --- Agent 의 결과 --------------------------------------------------------------

Route = Literal["grounded_draft", "escalation", "inspect_only"]
"""처리 경로. SOP-EA-01 9장.

grounded_draft  매뉴얼 판정 기준에 해당한다. 근거를 붙여 원인 후보와 점검 절차 초안을 쓴다
escalation      SOP-EA-01 6장의 조건(ESC-1~7)에 하나라도 걸린다. 초안 대신 사유와 근거를 넘긴다
inspect_only    판정 기준에 해당하지 않는 경고다. 점검 후 오탐 처리를 권한다(SOP-EA-01 8장)
"""


class CriterionResult(Strict):
    """매뉴얼 판정 기준 하나를 센서 값에 적용한 결과. **코드가 계산한다.**"""

    failure_type: FailureType
    rule: str
    measured: dict[str, float]
    met: bool
    citation: str = Field(description="판정 기준이 적힌 매뉴얼 절. 예: MC01-MM 4.2.2")


class EvidenceItem(Strict):
    """초안이 인용할 수 있는 근거. **검색·조회한 것만 들어온다.**"""

    evidence_id: str = Field(description="매뉴얼은 'MC01-MM 4.2.3', 이력은 'MR-0123'")
    kind: Literal["manual", "history"]
    reason: str = Field(description="왜 찾았는가. 예: 같은 유형 최근 기록")
    excerpt: str


class CauseCandidate(Strict):
    """원인 후보. **LLM 이 쓰되 근거 ID 가 없으면 받지 않는다.**"""

    rank: int = Field(ge=1)
    failure_type: HistoryFailureType
    rationale: str
    evidence_ids: list[str] = Field(min_length=1)


class InspectionStep(Strict):
    """점검·조치 단계. **LLM 이 쓰되 근거 ID 가 없으면 받지 않는다.**"""

    order: int = Field(ge=1)
    instruction: str
    evidence_ids: list[str] = Field(min_length=1)


class AgentResponse(Strict):
    """Agent 의 결과. 사람이 검토하기 전의 초안이다.

    코드가 채우는 필드: route, criteria_check, evidence, escalation_reasons, parts_to_prepare
    LLM 이 채우는 필드: cause_candidates, inspection_steps (grounded_draft 일 때만)
    escalation·inspect_only 는 문장까지 코드가 쓴다. drafted_by 가 그것을 밝힌다.
    """

    event_id: str
    route: Route
    criteria_check: list[CriterionResult]
    evidence: list[EvidenceItem]
    escalation_reasons: list[str] = Field(description="SOP-EA-01 6장 조건 코드. 예: ESC-2")
    cause_candidates: list[CauseCandidate]
    inspection_steps: list[InspectionStep]
    parts_to_prepare: list[str] = Field(description="근거에 나온 부품 번호")
    drafted_by: Literal["llm", "fixture_script", "code"]


class CompletedRepair(Strict):
    """이벤트를 처리해 조치를 끝낸 기록. 재발 판단(ESC-5)의 기준이다.

    경보가 연달아 온 것은 재발이 아니다. 같은 상태가 이어지면 30분마다 같은 경보가
    온다. **조치를 끝낸 뒤** 같은 유형이 다시 오는 것이 재발이다.
    """

    event_id: str
    failure_type: FailureType
    completed_at: str


class ReviewDecision(Strict):
    """정비 기술자의 검토 결과. 이것이 있어야 보고서가 된다(SOP-EA-01 7.2)."""

    decision: Literal["approve", "revise", "escalate", "reject"]
    reviewer_role: str = Field(min_length=1, max_length=40)
    note: str = Field(default="", max_length=400)


class MaintenanceReport(Strict):
    """정비 보고서. SOP-EA-01 7.1 의 항목을 그대로 따른다."""

    event_id: str
    equipment_id: str
    detected_at: str
    prediction: str = Field(description="예측 유형·확률·확신도를 한 줄로")
    criteria_summary: list[str]
    route: Route
    cause_candidates: list[CauseCandidate]
    inspection_steps: list[InspectionStep]
    parts_to_prepare: list[str]
    result: str = Field(description="점검·조치 결과. 초안 단계에서는 '점검 후 기입'")
    escalation: list[str]
    drafted_by: Literal["llm", "fixture_script", "code"]
    review: ReviewDecision


# --- API 요청·응답 ---------------------------------------------------------------

class CaseRequest(BaseModel):
    """데이터에 있는 카드는 event_id 로, 새 카드는 card 로 보낸다."""

    event_id: str | None = None
    card: EventCard | None = None
    completed_repairs: list[CompletedRepair] = Field(
        default_factory=list, description="앞서 조치를 끝낸 기록. 조치 후 재발(ESC-5) 판단에 쓴다")

    @model_validator(mode="after")
    def exactly_one(self):
        if (self.event_id is None) == (self.card is None):
            raise ValueError("event_id 와 card 중 하나만 보내세요.")
        return self


class CardSummary(BaseModel):
    event_id: str
    detected_at: str
    severity: str
    predicted_failure_type: str
    probability: float
    confidence_level: str
    candidates: list[str]
    scenario_id: str | None = Field(None, description="대표 사례면 S01~S10")
    teaching_point: str | None = None
    completed_repairs: list[CompletedRepair] = Field(
        default_factory=list, description="대표 사례가 가정하는 조치 완료 기록(S10)")


class CaseResponse(BaseModel):
    case_id: str
    mode: str
    status: str = Field(description="awaiting_review · reported · rejected")
    packet: dict | None = Field(None, description="검토 대기 중일 때 사람에게 보여 줄 것")
    queries: list[dict] = Field(default_factory=list, description="매뉴얼 검색 질의와 찾은 절")
    tool_calls: list[dict] = Field(default_factory=list, description="이력 담당 Agent 가 실제로 부른 Tool")
    filled_history_types: list[str] = Field(default_factory=list,
                                            description="Agent 가 빠뜨려 코드가 채운 이력 유형")
    report: MaintenanceReport | None = None
    report_markdown: str | None = None
    trace: list[str]
    thread_durability: str = Field(description="file 이면 재시작을 넘긴다. process_lifetime 이면 넘기지 못한다")
    # 실제 기록이다. 이 앱에는 설비를 제어하거나 작업 지시를 내는 경로가 없다.
    executed_actions: list[str] = Field(default_factory=list)
