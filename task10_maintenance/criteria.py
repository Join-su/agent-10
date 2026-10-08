"""매뉴얼 판정 기준(MC01-MM 부록 A)을 센서 값에 적용한다.

**모델의 예측과 별개로 계산한다.** 모델은 확률을 내고, 이 함수는 매뉴얼이 정한
기준에 해당하는지를 낸다. 둘이 다르면 그 차이가 escalation 사유가 된다(ESC-3).

HDF·PWF·OSF 의 기준은 AI4I 2020 의 고장 생성 조건과 같다. 그래서 이 계산은
fixture 에서도 진짜 결과다. TWF 는 위험 구간(200~240분)에서 무작위로 일어나므로
기준에 해당해도 고장이 아닐 수 있다.
"""
from __future__ import annotations

from task10_maintenance.domain import CriterionResult, SensorSnapshot

HDF_TEMP_DIFF_K = 8.6
HDF_RPM = 1380
PWF_MIN_W = 3500
PWF_MAX_W = 9000
OSF_LOAD_LIMIT = {"L": 11000, "M": 12000, "H": 13000}
TWF_RISK_MIN = 200
TWF_LIMIT_MIN = 240


def check_criteria(snapshot: SensorSnapshot, grade: str) -> list[CriterionResult]:
    """네 유형의 판정 기준을 모두 계산한다. 예측 유형만 보면 불일치를 못 찾는다."""
    wear, torque = snapshot.tool_wear_min, snapshot.torque_nm
    load = wear * torque
    limit = OSF_LOAD_LIMIT[grade]
    return [
        CriterionResult(
            failure_type="TWF",
            rule=f"공구 마모 {TWF_RISK_MIN}분 이상 (200~240 위험 구간, 240 초과 사용 한계)",
            measured={"tool_wear_min": wear},
            met=wear >= TWF_RISK_MIN,
            citation="MC01-MM 4.1.2",
        ),
        CriterionResult(
            failure_type="HDF",
            rule=f"온도 차 < {HDF_TEMP_DIFF_K} K 그리고 회전수 < {HDF_RPM:,} rpm",
            measured={"temp_diff_k": snapshot.temp_diff_k,
                      "rotational_speed_rpm": snapshot.rotational_speed_rpm},
            met=snapshot.temp_diff_k < HDF_TEMP_DIFF_K and snapshot.rotational_speed_rpm < HDF_RPM,
            citation="MC01-MM 4.2.2",
        ),
        CriterionResult(
            failure_type="PWF",
            rule=f"기계 출력 < {PWF_MIN_W:,} W 또는 > {PWF_MAX_W:,} W",
            measured={"power_w": snapshot.power_w},
            met=snapshot.power_w < PWF_MIN_W or snapshot.power_w > PWF_MAX_W,
            citation="MC01-MM 4.3.2",
        ),
        CriterionResult(
            failure_type="OSF",
            rule=f"부하 지수(마모 × 토크) > {limit:,} (품질 등급 {grade})",
            measured={"load_index": round(load, 1), "limit": float(limit)},
            met=load > limit,
            citation="MC01-MM 4.4.2",
        ),
    ]


def met_types(results: list[CriterionResult]) -> set[str]:
    return {r.failure_type for r in results if r.met}


def describe(result: CriterionResult) -> str:
    """보고서에 넣을 한 줄. 수치와 기준을 함께 적는다(SOP-EA-01 7.2)."""
    values = ", ".join(f"{k}={v:,.2f}" if isinstance(v, float) and not v.is_integer()
                       else f"{k}={v:,.0f}" for k, v in result.measured.items())
    verdict = "해당" if result.met else "해당 없음"
    return f"{result.failure_type}: {verdict} — {values} ({result.rule}, {result.citation})"
