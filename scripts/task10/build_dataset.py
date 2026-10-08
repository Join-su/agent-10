"""AI4I 2020 에서 과제 10 학습용 데이터를 만든다.

한 번 돌리면 `data/` 아래가 전부 다시 만들어진다. seed 가 고정이라 결과가 같다.

    uv run python scripts/task10/build_dataset.py --source <ai4i2020.csv 경로>

만드는 것
    data/source/ai4i2020.csv          원본 사본 (SHA-256 확인)
    data/eventcards/eventcards.jsonl  ML 이 만든 이상 이벤트 — Agent 의 입력
    data/eventcards/scenarios.jsonl   경로별 대표 사례 10건 (build_scenarios.py)
    data/eval/                        정답·놓친 고장·사례 기대 경로 — 평가 전용, Agent 에게 주지 않는다
    data/history/                     MC-01 정비 이력 (JSONL. Postgres 적재는 load_history.py)
    data/model/model_card.json        모델 계수·임계값·검증 지표
    data/manuals/md/ML-GUIDE-01.md    모델 해석 안내서 (검증 지표를 채워 생성)
    schemas/*.json                    domain.py 에서 생성한 JSON Schema
    data/manifest.json                건수·해시·분할 정보

**모델은 numpy 로 학습한 로지스틱 회귀다.** scikit-learn 을 쓰지 않은 것은 v2
환경에 없어서다. 이 스크립트는 학습 자료가 아니라 입력 데이터를 만드는 도구이고,
학습자가 배우는 대상은 EventCard 를 받은 뒤의 처리다.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2] / "task10_maintenance"
sys.path.insert(0, str(ROOT.parent))

from task10_maintenance.domain import (  # noqa: E402
    AgentResponse,
    CompletedRepair,
    EventCard,
    EventTruth,
    MaintenanceRecord,
    MaintenanceReport,
    ReviewDecision,
)

SOURCE_SHA256 = "dc6630cd9b1f0f853922fad78a1b6436570d3f1ec863f1dd5c4340ac56bc8a8e"
SEED = 7
OPERATION_SHARE = 0.3
MODEL_ID = "pdm-logreg-v1"
EQUIPMENT = "MC-01"
KST = timezone(timedelta(hours=9))
START = datetime(2025, 3, 3, 6, 0, tzinfo=KST)
MINUTES_PER_ROW = 30

TYPES = ["TWF", "HDF", "PWF", "OSF"]
ALL_TYPES = TYPES + ["RNF"]
# TWF 는 확률이 낮게 나오는 유형이라 따로 낮춘다. ML-GUIDE-01 4.1 에 적는다.
THRESHOLDS = {"TWF": 0.10, "HDF": 0.40, "PWF": 0.40, "OSF": 0.40}
OSF_LIMIT = {"L": 11000, "M": 12000, "H": 13000}
TECHNICIANS = ["정비기술자 A", "정비기술자 B", "정비기술자 C", "정비기술자 D"]

FEATURES = ["air_temperature_k", "process_temperature_k", "rotational_speed_rpm",
            "torque_nm", "tool_wear_min", "temp_diff_k", "power_w", "quality_grade",
            "power_w_extreme", "load_index"]

PARTS = {
    "PN-TL-1008": "엔드밀 공구 Ø10",
    "PN-TH-2201": "공구 홀더 콜릿",
    "PN-CF-3105": "스핀들 냉각팬 모듈",
    "PN-FL-3120": "흡기 필터",
    "PN-HS-3150": "방열 서멀 패드",
    "PN-IV-4410": "인버터 제어 보드",
    "PN-PS-4420": "전원 단자 퓨즈 세트",
    "PN-EN-4430": "스핀들 엔코더",
    "PN-BR-5510": "스핀들 베어링 세트",
    "PN-CL-5520": "절삭유 노즐",
}


# --- 원본과 분할 ---------------------------------------------------------------

def load_source(path: Path) -> pd.DataFrame:
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    if digest != SOURCE_SHA256:
        raise SystemExit(f"AI4I 원본 해시가 다릅니다: {digest}")
    df = pd.read_csv(path)
    df.columns = ["udi", "product_id", "grade", "air", "proc", "rpm", "torque", "wear",
                  "mf", "TWF", "HDF", "PWF", "OSF", "RNF"]
    df["temp_diff"] = df.proc - df.air
    df["power"] = df.torque * df.rpm * 2 * np.pi / 60
    df["load"] = df.wear * df.torque
    df["cycle"] = np.concatenate([[0], np.cumsum(np.diff(df.wear.values) < 0)])
    return df


def split_cycles(df: pd.DataFrame, rng: np.random.Generator) -> pd.DataFrame:
    """공구 교체 주기 단위로 나눈다. 같은 주기의 이웃 행이 양쪽에 섞이지 않게.

    HDF 는 원본 앞쪽 6,000행에만 있다. 행 순서로 자르면 운영 구간에 HDF 가 없다.
    그래서 주기마다 가장 드문 유형으로 층을 나누고 층마다 30%를 운영으로 보낸다.
    """
    per_cycle = df.groupby("cycle")[TYPES].sum()

    def stratum(row):
        for t in ["HDF", "TWF", "PWF", "OSF"]:
            if row[t] > 0:
                return t
        return "none"

    per_cycle["stratum"] = per_cycle.apply(stratum, axis=1)
    operation: list[int] = []
    for _, group in per_cycle.groupby("stratum"):
        ids = group.index.values.copy()
        rng.shuffle(ids)
        operation += list(ids[:max(1, round(len(ids) * OPERATION_SHARE))])
    df["split"] = np.where(df.cycle.isin(operation), "operation", "history")
    return df


def assign_time(df: pd.DataFrame) -> pd.DataFrame:
    """이력 주기를 앞 기간, 운영 주기를 뒤 기간에 놓고 30분 간격으로 시각을 붙인다.

    UCI 는 행 순서를 시간 순서라고 밝히지 않는다. 그래서 주기 안의 순서(공구 마모가
    늘어나는 순서)만 지키고 주기의 배치는 분할에 맞춰 다시 정한다.
    """
    order = pd.concat([df[df.split == "history"].sort_values(["cycle", "udi"]),
                       df[df.split == "operation"].sort_values(["cycle", "udi"])])
    order = order.assign(seq=np.arange(len(order)))
    order["at"] = [START + timedelta(minutes=MINUTES_PER_ROW * int(s)) for s in order.seq]
    return order.sort_values("seq").reset_index(drop=True)


# --- 모델 -----------------------------------------------------------------------

class Model:
    """유형별 로지스틱 회귀(one-vs-rest). 표준화는 학습 구간 통계로 한다."""

    def __init__(self, frame: pd.DataFrame):
        raw = self._raw(frame)
        self.mean = raw.mean(0)
        self.std = raw.std(0)
        self.reference = {
            "air_temperature_k": frame.air.mean(), "process_temperature_k": frame.proc.mean(),
            "rotational_speed_rpm": frame.rpm.mean(), "torque_nm": frame.torque.mean(),
            "tool_wear_min": frame.wear.mean(), "temp_diff_k": frame.temp_diff.mean(),
            "power_w": frame.power.mean(), "quality_grade": 0.0,
            "power_w_extreme": frame.power.mean(), "load_index": frame.load.mean(),
        }
        z = self.design(frame)
        self.weights = {t: self._fit(z, frame[t].values.astype(float)) for t in TYPES}

    @staticmethod
    def _raw(frame: pd.DataFrame) -> np.ndarray:
        grade = frame.grade.map({"L": 0, "M": 1, "H": 2}).values
        return np.column_stack([frame.air, frame.proc, frame.rpm, frame.torque, frame.wear,
                                frame.temp_diff, frame.power, grade])

    def design(self, frame: pd.DataFrame) -> np.ndarray:
        z = (self._raw(frame) - self.mean) / self.std
        power_extreme = z[:, 6] ** 2                        # 출력의 양쪽 끝
        load = (frame.load.values / 1000.0 - 4.3) / 2.5      # 마모 × 토크
        return np.column_stack([z, power_extreme, load])

    @staticmethod
    def _fit(z: np.ndarray, y: np.ndarray, l2: float = 1e-2, steps: int = 5000,
             lr: float = 0.3) -> tuple[np.ndarray, float]:
        # 고장이 드물어 그대로 학습하면 전부 정상으로 맞힌다. 약하게(1/4 제곱) 가중한다.
        positive = ((len(y) - y.sum()) / max(y.sum(), 1)) ** 0.25
        sample = np.where(y == 1, positive, 1.0)
        sample = sample / sample.mean()
        w, b = np.zeros(z.shape[1]), 0.0
        for _ in range(steps):
            p = 1 / (1 + np.exp(-(z @ w + b)))
            g = (p - y) * sample
            w -= lr * (z.T @ g / len(y) + l2 * w)
            b -= lr * g.mean()
        return w, b

    def predict(self, frame: pd.DataFrame) -> tuple[np.ndarray, np.ndarray]:
        z = self.design(frame)
        p = np.column_stack([1 / (1 + np.exp(-(z @ w + b)))
                             for w, b in (self.weights[t] for t in TYPES)])
        return p, z


def raw_value(row, feature: str) -> float:
    return {
        "air_temperature_k": row.air, "process_temperature_k": row.proc,
        "rotational_speed_rpm": row.rpm, "torque_nm": row.torque, "tool_wear_min": row.wear,
        "temp_diff_k": row.temp_diff, "power_w": row.power,
        "quality_grade": {"L": 0, "M": 1, "H": 2}[row.grade],
        "power_w_extreme": row.power, "load_index": row.load,
    }[feature]


def decide(p_row: np.ndarray) -> tuple[list[str], str | None]:
    candidates = [t for i, t in enumerate(TYPES) if p_row[i] >= THRESHOLDS[t]]
    if not candidates:
        return [], None
    predicted = max(candidates, key=lambda t: p_row[TYPES.index(t)] / THRESHOLDS[t])
    return candidates, predicted


def confidence(p: float) -> str:
    return "high" if p >= 0.8 else "medium" if p >= 0.5 else "low"


def validation_metrics(history: pd.DataFrame, rng: np.random.Generator) -> dict:
    """이력 구간 안에서 주기 20%를 떼어 검증한다. 운영 구간의 정답은 쓰지 않는다."""
    cycles = history.cycle.unique().copy()
    rng.shuffle(cycles)
    held = set(cycles[: max(1, round(len(cycles) * 0.2))])
    train, valid = history[~history.cycle.isin(held)], history[history.cycle.isin(held)]
    model = Model(train)
    p, _ = model.predict(valid)
    out = {}
    for i, t in enumerate(TYPES):
        flag = p[:, i] >= THRESHOLDS[t]
        actual = valid[t].values == 1
        tp = int((flag & actual).sum())
        out[t] = {
            "threshold": THRESHOLDS[t],
            "support": int(actual.sum()),
            "flagged": int(flag.sum()),
            "precision": round(tp / flag.sum(), 3) if flag.sum() else None,
            "recall": round(tp / actual.sum(), 3) if actual.sum() else None,
        }
    out["_rows"] = int(len(valid))
    return out


# --- EventCard 와 평가 정답 -----------------------------------------------------

def build_events(operation: pd.DataFrame, model: Model):
    p, z = model.predict(operation)
    cards, truths, missed = [], [], []
    for i, row in enumerate(operation.itertuples(index=False)):
        actual = [t for t in ALL_TYPES if getattr(row, t) == 1]
        candidates, predicted = decide(p[i])
        if predicted is None:
            if row.mf == 1:
                missed.append({"row_id": str(row.udi), "at": row.at.isoformat(),
                               "actual_failure_types": actual or ["UNKNOWN"]})
            continue

        k = TYPES.index(predicted)
        w, _ = model.weights[predicted]
        contrib = w * z[i]
        top = np.argsort(-contrib)[:3]
        signals = [{"feature": FEATURES[j], "value": round(float(raw_value(row, FEATURES[j])), 1),
                    "reference": round(float(model.reference[FEATURES[j]]), 1),
                    "contribution": round(float(contrib[j]), 3)} for j in top]
        event_id = f"EVT-2025-{len(cards) + 1:04d}"
        card = EventCard(
            event_id=event_id, equipment_id=EQUIPMENT, detected_at=row.at.isoformat(),
            severity="alarm" if p[i, k] >= 0.5 else "warning",
            product_id=row.product_id, quality_grade=row.grade,
            sensor_snapshot=snapshot(row),
            prediction={
                "model_id": MODEL_ID, "predicted_failure_type": predicted,
                "probabilities": {t: round(float(p[i, j]), 3) for j, t in enumerate(TYPES)},
                "thresholds": THRESHOLDS, "candidates": candidates,
                "confidence_level": confidence(float(p[i, k])), "top_signals": signals,
            },
            data_lineage={"source": "ai4i2020", "row_id": str(row.udi), "cycle": str(row.cycle)},
        )
        if (row.mf == 1) != bool(actual):
            case = "label_inconsistent"
        elif row.mf == 0:
            case = "false_alarm"
        elif predicted in actual:
            case = "correct"
        else:
            case = "type_mismatch"
        truths.append(EventTruth(event_id=event_id, machine_failure=bool(row.mf),
                                 actual_failure_types=actual or (["UNKNOWN"] if row.mf else []),
                                 prediction_correct=case == "correct", case=case))
        cards.append(card)
    return cards, truths, missed


def snapshot(row) -> dict:
    return {"air_temperature_k": float(row.air), "process_temperature_k": float(row.proc),
            "rotational_speed_rpm": float(row.rpm), "torque_nm": float(row.torque),
            "tool_wear_min": float(row.wear), "temp_diff_k": round(float(row.temp_diff), 2),
            "power_w": round(float(row.power), 0)}


# --- 정비 이력 ------------------------------------------------------------------

def part(no: str, qty: int = 1) -> dict:
    return {"part_no": no, "name": PARTS[no], "qty": qty}


def describe_failure(t: str, row, rng: np.random.Generator) -> dict:
    """유형별 증상·판단·조치. 매뉴얼(MC01-MM) 4장의 기준과 절 번호에 맞춘다."""
    if t == "TWF":
        in_window = 200 <= row.wear <= 240
        holder = rng.random() < 0.3
        return {
            "symptom": str(rng.choice(["가공면 거칠기 불량 후 공구 날 끝 파손으로 정지",
                                       "절삭음이 커진 뒤 공구 파손으로 정지",
                                       "치수 불량이 연속 발생해 운전자가 공구 이상을 보고"])),
            "diagnosis": (f"공구 마모 {row.wear:.0f}분으로 위험 구간(200~240분). 날 끝 치핑 확인"
                          if in_window else
                          f"공구 마모 {row.wear:.0f}분으로 사용 한계(240분) 초과. 날 끝 파손 확인"
                          if row.wear > 240 else
                          f"공구 마모 {row.wear:.0f}분, 날 끝 파손 확인. 위험 구간(200분) 전에 발생"),
            "action": "공구 교체, 마모 카운터 초기화, 시험 가공 치수 확인"
                      + (", 콜릿 균열로 함께 교체" if holder else ", 콜릿 칩 청소"),
            "parts": [part("PN-TL-1008")] + ([part("PN-TH-2201")] if holder else []),
            "downtime": int(rng.integers(25, 51)),
            "refs": ["MC01-MM 4.1.3", "MC01-MM 5.1"],
        }
    if t == "HDF":
        cause = rng.choice(["filter", "fan", "pad"], p=[0.5, 0.3, 0.2])
        detail = {"filter": ("흡기 필터 압력차 적색(막힘)", "흡기 필터 교체", "PN-FL-3120", "MC01-MM 5.3"),
                  "fan": ("냉각팬 1기 정지", "냉각팬 모듈 교체", "PN-CF-3105", "MC01-MM 5.2"),
                  "pad": ("서멀 패드 경화", "서멀 패드 교체", "PN-HS-3150", "MC01-MM 4.2.4")}[cause]
        return {
            "symptom": str(rng.choice(["저속 가공 중 스핀들 하우징 과열로 정지",
                                       "온도 경고 후 스핀들 정지",
                                       "하우징이 평소보다 뜨겁다는 운전자 보고 후 정지"])),
            "diagnosis": (f"온도 차 {row.temp_diff:.2f} K(기준 8.6 K 미만), 회전수 {row.rpm:.0f} rpm"
                          f"(기준 1,380 rpm 미만). {detail[0]}"),
            "action": f"{detail[1]}, 10분 시운전 후 온도 차 회복 확인",
            "parts": [part(detail[2])],
            "downtime": int(rng.integers(45, 121)),
            "refs": ["MC01-MM 4.2.3", detail[3]],
        }
    if t == "PWF":
        if row.power < 3500:
            cause = rng.choice(["terminal", "encoder"], p=[0.7, 0.3])
            detail = {"terminal": ("전원 단자대 이완·변색", "퓨즈 세트 교체 후 재체결", "PN-PS-4420"),
                      "encoder": ("엔코더 신호 케이블 피복 손상", "엔코더 교체", "PN-EN-4430")}[cause]
            diagnosis = f"출력 {row.power:,.0f} W(3,500 W 미만, 출력 부족). {detail[0]}"
            refs = ["MC01-MM 4.3.3", "MC01-MM 4.3.4"]
        else:
            cause = rng.choice(["condition", "inverter"], p=[0.6, 0.4])
            detail = {"condition": ("절삭 조건이 공정 표준 초과", "공정 담당 협의 후 이송 속도 하향",
                                    None),
                      "inverter": ("인버터 과전류 이력 반복", "인버터 리셋, 제어 보드 교체",
                                   "PN-IV-4410")}[cause]
            diagnosis = f"출력 {row.power:,.0f} W(9,000 W 초과, 출력 과다). {detail[0]}"
            refs = ["MC01-MM 4.3.3", "MC01-MM 5.5"]
        return {
            "symptom": str(rng.choice(["인버터 트립으로 스핀들 정지", "절삭 중 회전수 급락 후 정지",
                                       "인버터 경고 표시 후 정지"])),
            "diagnosis": diagnosis,
            "action": f"LOTO 후 점검. {detail[1]}",
            "parts": [part(detail[2])] if detail[2] else [],
            "downtime": int(rng.integers(60, 181)),
            "refs": refs,
        }
    if t == "OSF":
        limit = OSF_LIMIT[row.grade]
        bearing = rng.random() < 0.15
        nozzle = rng.random() < 0.3
        action = "공구 교체" + (", 절삭유 노즐 청소" if nozzle else "") + \
                 (", 베어링 진동 기준 초과로 정비 엔지니어에 베어링 점검 요청" if bearing else "")
        return {
            "symptom": str(rng.choice(["절삭 중 토크 급증 후 스핀들 정지",
                                       "떨림 자국 발생 후 과부하 정지",
                                       "공구 날 깨짐과 함께 과부하 정지"])),
            "diagnosis": (f"부하 지수 {row.load:,.0f} 분·Nm(등급 {row.grade} 한계 {limit:,} 초과). "
                          f"공구 마모 {row.wear:.0f}분, 토크 {row.torque:.1f} Nm"),
            "action": action,
            "parts": [part("PN-TL-1008")] + ([part("PN-CL-5520")] if nozzle else []),
            "downtime": int(rng.integers(30, 91)) + (60 if bearing else 0),
            "refs": ["MC01-MM 4.4.3", "MC01-MM 5.1"] + (["MC01-MM 5.4"] if bearing else []),
        }
    # RNF 와 원인 미상
    return {
        "symptom": "운전 중 갑작스러운 정지",
        "diagnosis": "정지 직전 센서 값이 판정 기준(MC01-MM 부록 A) 어디에도 해당하지 않음",
        "action": "점검 후 이상 부위 미발견, 재가동. 정비 엔지니어 검토 요청",
        "parts": [],
        "downtime": int(rng.integers(30, 121)),
        "refs": ["MC01-MM 4.5", "SOP-EA-01 6"],
    }


def false_alarm_finding(t: str, row) -> tuple[str, str]:
    """오탐 점검 결과를 판정 기준 수치와 함께 적는다(SOP-EA-01 8).

    HDF·PWF·OSF 는 AI4I 에서 조건식으로 정해지므로 고장이 없었다면 기준에도 해당하지
    않는다. TWF 는 다르다. 위험 구간(200~240분) 안이라도 고장이 안 날 수 있고, 240분을
    넘긴 채 운전하는 경우도 있다. 그 경우를 "해당 없음"이라고 적으면 매뉴얼과 모순된다.
    """
    if t == "TWF":
        if row.wear > 240:
            return (f"고장 징후 없음. 다만 공구 마모 {row.wear:.0f}분으로 사용 한계(240분) 초과",
                    "육안·청음 점검 이상 없음. 교체 지연 사유를 기록하고 정비 엔지니어에 보고")
        if row.wear >= 200:
            return (f"고장 징후 없음. 공구 마모 {row.wear:.0f}분으로 위험 구간(200~240분), 날 끝 정상",
                    "육안·청음 점검 이상 없음. 다음 공구 교체 시점 확인")
        return (f"판정 기준 해당 없음: 공구 마모 {row.wear:.0f}분, 날 끝 정상",
                "육안·청음 점검, 이상 없음. 조치 없음")
    note = {
        "HDF": f"온도 차 {row.temp_diff:.2f} K, 회전수 {row.rpm:.0f} rpm — 두 조건 동시 성립 안 함",
        "PWF": f"출력 {row.power:,.0f} W — 3,500 ~ 9,000 W 안",
        "OSF": f"부하 지수 {row.load:,.0f} 분·Nm — 등급 {row.grade} 한계 {OSF_LIMIT[row.grade]:,} 이하",
    }[t]
    return f"판정 기준 해당 없음: {note}", "육안·청음 점검, 이상 없음. 조치 없음"


def build_history(history: pd.DataFrame, operation: pd.DataFrame, model: Model, rng: np.random.Generator):
    p, _ = model.predict(history)
    drafts = []
    for i, row in enumerate(history.itertuples(index=False)):
        candidates, predicted = decide(p[i])
        alarm = ({"predicted_failure_type": predicted,
                  "probability": round(float(p[i, TYPES.index(predicted)]), 3)}
                 if predicted else None)
        if row.mf == 1:
            types = [t for t in ALL_TYPES if getattr(row, t) == 1] or ["UNKNOWN"]
            parts_ = [describe_failure(t, row, rng) for t in types]
            multi = len(types) > 1
            drafts.append({
                "at": row.at + timedelta(minutes=5), "record_type": "failure_repair",
                "trigger": "ml_alarm" if alarm else "operator_report", "past_alarm": alarm,
                "failure_types": types, "row": row,
                "symptom": parts_[0]["symptom"] if not multi else "복합 증상: " + " / ".join(x["symptom"] for x in parts_),
                "diagnosis": " | ".join(x["diagnosis"] for x in parts_),
                "action": " | ".join(x["action"] for x in parts_),
                "parts": dedupe([pp for x in parts_ for pp in x["parts"]]),
                "downtime": sum(x["downtime"] for x in parts_),
                "outcome": "정비 엔지니어 확인 후 재가동" if multi or types[0] in ("RNF", "UNKNOWN")
                           else str(rng.choice(["시운전 정상, 재가동", "재가동, 직전 가공품 2개 격리",
                                                "재가동, 다음 교대 재점검 예정"])),
                "refs": dedupe([r for x in parts_ for r in x["refs"]] + (["MC01-MM 4.6"] if multi else [])),
            })
        elif alarm and not any(getattr(row, t) for t in ALL_TYPES):
            t = alarm["predicted_failure_type"]
            diagnosis, action = false_alarm_finding(t, row)
            drafts.append({
                "at": row.at + timedelta(minutes=10), "record_type": "false_alarm_check",
                "trigger": "ml_alarm", "past_alarm": alarm, "failure_types": [], "row": row,
                "symptom": f"ML {'경보' if alarm['probability'] >= 0.5 else '경고'}({t} 예측, 확률 {alarm['probability']:.2f}) 접수",
                "diagnosis": diagnosis,
                "action": action,
                "parts": [], "downtime": int(rng.integers(10, 26)), "outcome": "정상 운전 유지",
                "refs": ["SOP-EA-01 8", {"TWF": "MC01-MM 4.1.2", "HDF": "MC01-MM 4.2.2",
                                         "PWF": "MC01-MM 4.3.2", "OSF": "MC01-MM 4.4.2"}[t]],
            })

    # 주기의 마지막 행 = 공구를 바꾼 시점. 공구 파손 수리로 끝난 주기는 수리 기록이 대신한다.
    last_rows = history.groupby("cycle").tail(1)
    for row in last_rows.itertuples(index=False):
        if row.mf == 1 and (row.TWF == 1 or row.OSF == 1):
            continue
        over = row.wear > 240
        drafts.append({
            "at": row.at + timedelta(minutes=20), "record_type": "tool_change",
            "trigger": "scheduled", "past_alarm": None, "failure_types": [], "row": row,
            "symptom": f"정기 공구 교체(마모 {row.wear:.0f}분)",
            "diagnosis": "사용 한계(240분) 초과 마모" if over else "날 끝 정상 마모",
            "action": "공구 교체, 마모 카운터 초기화",
            "parts": [part("PN-TL-1008")], "downtime": int(rng.integers(15, 26)),
            "outcome": "교체 완료", "refs": ["MC01-MM 5.1"],
        })

    # 운영 기간에는 공구 교체 기록만 남긴다. 교체 기록은 고장과 무관하게 남는 기록이라
    # 정답이 새지 않는다(교체 사유는 적지 않는다). 이것이 없으면 9월 이벤트의 "마지막
    # 공구 교체"가 7월 이력 끝으로 나와, 마모 20분짜리 공구와 어긋난다.
    # 운영 기간의 고장 수리·오탐 기록은 평가 정답과 겹치므로 넣지 않는다.
    for row in operation.groupby("cycle").tail(1).itertuples(index=False):
        drafts.append({
            "at": row.at + timedelta(minutes=20), "record_type": "tool_change",
            "trigger": "scheduled", "past_alarm": None, "failure_types": [], "row": row,
            "symptom": f"공구 교체(마모 {row.wear:.0f}분)",
            "diagnosis": "운영 기간 공구 교체 기록 — 교체 사유 미기재",
            "action": "공구 교체, 마모 카운터 초기화",
            "parts": [part("PN-TL-1008")], "downtime": int(rng.integers(15, 26)),
            "outcome": "교체 완료", "refs": ["MC01-MM 5.1"],
        })

    drafts.sort(key=lambda d: d["at"])
    records = []
    for n, d in enumerate(drafts, start=1):
        row = d["row"]
        records.append(MaintenanceRecord(
            record_id=f"MR-{n:04d}", equipment_id=EQUIPMENT, occurred_at=d["at"].isoformat(),
            record_type=d["record_type"], trigger=d["trigger"], past_alarm=d["past_alarm"],
            failure_types=d["failure_types"], quality_grade=row.grade,
            sensor_snapshot=snapshot(row), symptom=d["symptom"], diagnosis=d["diagnosis"],
            action=d["action"], parts_replaced=d["parts"], downtime_min=d["downtime"],
            outcome=d["outcome"], manual_refs=d["refs"],
            technician=str(rng.choice(TECHNICIANS)),
            source={"row_id": str(row.udi), "cycle": str(row.cycle)},
            provenance="synthetic_from_ai4i2020",
        ))
    return records


def dedupe(items: list) -> list:
    seen, out = set(), []
    for item in items:
        key = json.dumps(item, sort_keys=True, ensure_ascii=False)
        if key not in seen:
            seen.add(key)
            out.append(item)
    return out


# --- 대표 사례와 안내서 ---------------------------------------------------------

def write_guide(path: Path, metrics: dict, history: pd.DataFrame, operation_start: str) -> None:
    template = (Path(__file__).with_name("ml_guide_template.md")).read_text(encoding="utf-8")
    rows = []
    for t in TYPES:
        m = metrics[t]
        fmt = lambda v: "-" if v is None else f"{v:.2f}"  # noqa: E731
        rows.append(f"| {t} | {m['threshold']:.2f} | {m['support']} | {m['flagged']} | "
                    f"{fmt(m['precision'])} | {fmt(m['recall'])} |")
    text = template.format(
        model_id=MODEL_ID,
        train_from=history["at"].min().strftime("%Y-%m-%d"),
        train_to=history["at"].max().strftime("%Y-%m-%d"),
        train_rows=f"{len(history):,}",
        valid_rows=f"{metrics['_rows']:,}",
        issued=operation_start[:10],
        metric_rows="\n".join(rows),
    )
    path.write_text(text, encoding="utf-8")


def write_jsonl(path: Path, items) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for item in items:
            data = item.model_dump(mode="json") if hasattr(item, "model_dump") else item
            f.write(json.dumps(data, ensure_ascii=False) + "\n")


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--source", type=Path, default=ROOT / "data" / "source" / "ai4i2020.csv")
    args = parser.parse_args()

    data = ROOT / "data"
    source_copy = data / "source" / "ai4i2020.csv"
    source_copy.parent.mkdir(parents=True, exist_ok=True)
    if args.source.resolve() != source_copy.resolve():
        shutil.copyfile(args.source, source_copy)

    rng = np.random.default_rng(SEED)
    df = assign_time(split_cycles(load_source(source_copy), rng))
    history, operation = df[df.split == "history"], df[df.split == "operation"]

    metrics = validation_metrics(history, np.random.default_rng(SEED + 1))
    model = Model(history)
    cards, truths, missed = build_events(operation, model)
    records = build_history(history, operation, model, np.random.default_rng(SEED + 2))

    write_jsonl(data / "eventcards" / "eventcards.jsonl", cards)
    write_jsonl(data / "eval" / "event_truth.jsonl", truths)
    write_jsonl(data / "eval" / "missed_failures.jsonl", missed)
    write_jsonl(data / "history" / "maintenance_history.jsonl", records)

    (data / "model").mkdir(parents=True, exist_ok=True)
    (data / "model" / "model_card.json").write_text(json.dumps({
        "model_id": MODEL_ID, "kind": "one-vs-rest logistic regression (numpy)",
        "features": FEATURES, "thresholds": THRESHOLDS,
        "standardization": {"mean": model.mean.round(4).tolist(), "std": model.std.round(4).tolist()},
        "weights": {t: {"coef": w.round(4).tolist(), "intercept": round(float(b), 4)}
                    for t, (w, b) in model.weights.items()},
        "validation": metrics,
        "trained_on": {"split": "history", "rows": int(len(history))},
        "not_predicted": ["RNF"],
    }, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    write_guide(data / "manuals" / "md" / "ML-GUIDE-01.md", metrics, history,
                operation["at"].min().isoformat())

    schemas = ROOT / "schemas"
    schemas.mkdir(exist_ok=True)
    for model_cls in (EventCard, MaintenanceRecord, EventTruth, CompletedRepair,
                      AgentResponse, ReviewDecision, MaintenanceReport):
        (schemas / f"{model_cls.__name__}.json").write_text(
            json.dumps(model_cls.model_json_schema(), ensure_ascii=False, indent=1) + "\n",
            encoding="utf-8")

    # 대표 사례는 카드에서 고르므로 카드를 다시 만들면 함께 다시 고른다. manifest 보다 먼저.
    sys.path.insert(0, str(Path(__file__).parent))
    from build_scenarios import main as build_scenarios
    build_scenarios()

    counts = lambda items, key: pd.Series([key(x) for x in items]).value_counts().to_dict()  # noqa: E731
    outputs = [p for p in sorted(data.rglob("*")) if p.is_file() and p.name != "manifest.json"
               and "index" not in p.parts and "pdf" not in p.parts]
    (data / "manifest.json").write_text(json.dumps({
        "source": {"name": "UCI AI4I 2020 Predictive Maintenance Dataset",
                   "license": "CC BY 4.0", "sha256": SOURCE_SHA256},
        "seed": SEED,
        "split": {"unit": "tool_wear_cycle", "operation_share": OPERATION_SHARE,
                  "history_rows": int(len(history)), "operation_rows": int(len(operation)),
                  "history_period": [history["at"].min().isoformat(), history["at"].max().isoformat()],
                  "operation_period": [operation["at"].min().isoformat(), operation["at"].max().isoformat()]},
        "eventcards": {"total": len(cards),
                       "by_predicted_type": counts(cards, lambda c: c.prediction.predicted_failure_type),
                       "by_confidence": counts(cards, lambda c: c.prediction.confidence_level),
                       "by_case": counts(truths, lambda t: t.case),
                       "missed_failures": len(missed)},
        "history": {"total": len(records), "by_record_type": counts(records, lambda r: r.record_type),
                    "by_failure_type": counts([t for r in records for t in r.failure_types], lambda t: t)},
        "files": {str(p.relative_to(ROOT)): sha(p) for p in outputs},
    }, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")

    print(f"EventCard {len(cards)}장 · 놓친 고장 {len(missed)}건 · 정비 이력 {len(records)}건")


if __name__ == "__main__":
    main()
