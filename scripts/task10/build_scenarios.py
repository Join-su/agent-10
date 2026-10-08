"""Notebook 과 테스트에서 쓸 대표 사례를 고른다.

    uv run python scripts/task10/build_scenarios.py

**카드는 지어내지 않는다.** 전부 `eventcards.jsonl` 의 실제 카드다. 자연 데이터에
없는 상황(조치 후 재발, ESC-5)만 "앞 이벤트를 조치했다"는 맥락을 붙여 만든다.
ESC-4(근거 없음)는 데이터로 만들 수 없어 테스트에서 근거를 비워 확인한다.

만드는 것
    data/eventcards/scenarios.jsonl   사례별 카드와 맥락 (Agent 입력)
    data/eval/scenario_index.json     사례별 기대 경로·사유·정답·학습 포인트 (평가 전용)

기대 경로는 SOP-EA-01 6·9장을 읽고 사례마다 적은 것이다. `core.decide_route` 가
그것과 같은 답을 내는지는 테스트가 확인한다.
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2] / "task10_maintenance"
sys.path.insert(0, str(ROOT.parent))

from task10_maintenance.domain import EventCard  # noqa: E402
from task10_maintenance.criteria import check_criteria, met_types  # noqa: E402

DATA = ROOT / "data"


def load():
    cards = [EventCard.model_validate_json(line)
             for line in (DATA / "eventcards" / "eventcards.jsonl").read_text(encoding="utf-8").splitlines()]
    truth = {t["event_id"]: t for t in (json.loads(line) for line in
             (DATA / "eval" / "event_truth.jsonl").read_text(encoding="utf-8").splitlines())}
    return cards, truth


def met(card: EventCard) -> set[str]:
    return met_types(check_criteria(card.sensor_snapshot, card.quality_grade))


def first(cards, truth, test):
    for card in cards:
        if test(card, truth[card.event_id]):
            return card
    raise SystemExit("조건에 맞는 카드가 없습니다. 데이터가 바뀌었는지 확인하세요.")


def main() -> None:
    cards, truth = load()
    p = lambda c: c.prediction  # noqa: E731
    single = lambda c: len(p(c).candidates) == 1  # noqa: E731

    slots = [
        ("S01", "grounded_draft", [], "HDF 정탐 — 판정 기준 두 조건이 모두 성립",
         lambda c, t: p(c).predicted_failure_type == "HDF" and single(c) and t["case"] == "correct"
         and "HDF" in met(c)),
        ("S02", "grounded_draft", [], "PWF 정탐·높은 확신 — 출력 범위 이탈",
         lambda c, t: p(c).predicted_failure_type == "PWF" and single(c) and t["case"] == "correct"
         and p(c).confidence_level == "high"),
        ("S03", "grounded_draft", [], "OSF 정탐 — 부하 지수가 등급 한계 초과",
         lambda c, t: p(c).predicted_failure_type == "OSF" and single(c) and t["case"] == "correct"
         and met(c) == {"OSF"}),
        ("S04", "grounded_draft", [], "TWF 정탐·낮은 확신 — 확률보다 마모 시간과 교체 기록으로 판단",
         lambda c, t: p(c).predicted_failure_type == "TWF" and single(c) and t["case"] == "correct"
         and "TWF" in met(c)),
        ("S05", "grounded_draft", [], "TWF 오탐인데 기준은 성립 — 경로로는 못 거르고 사람이 걸러야 함",
         lambda c, t: p(c).predicted_failure_type == "TWF" and single(c) and t["case"] == "false_alarm"
         and met(c) == {"TWF"}),
        ("S06", "inspect_only", ["SOP-EA-01 8"], "HDF 경고 오탐 — 어떤 기준에도 해당하지 않음",
         lambda c, t: p(c).predicted_failure_type == "HDF" and c.severity == "warning" and not met(c)),
        ("S07", "escalation", ["ESC-2"], "복합 후보 — 후보 유형의 판정 기준이 모두 성립",
         lambda c, t: len(p(c).candidates) >= 2 and t["case"] == "correct"
         and set(p(c).candidates) <= met(c)),
        ("S08", "escalation", ["ESC-3"], "예측과 판정 불일치 — 예측 유형 기준은 아니고 다른 유형 기준에 해당",
         lambda c, t: single(c) and met(c) and p(c).predicted_failure_type not in met(c)),
        ("S09", "escalation", ["ESC-7"], "경보인데 어떤 기준에도 해당하지 않음",
         lambda c, t: single(c) and c.severity == "alarm" and not met(c)),
    ]

    lines, index = [], []
    for scenario_id, route, reasons, point, test in slots:
        card = first(cards, truth, test)
        lines.append({"scenario_id": scenario_id, "card": card.model_dump(mode="json"),
                      "completed_repairs": []})
        if scenario_id == "S07":
            point = f"{point} ({' + '.join(p(card).candidates)})"
        index.append({"scenario_id": scenario_id, "event_id": card.event_id,
                      "expected_route": route, "expected_reasons": reasons,
                      "truth_case": truth[card.event_id]["case"],
                      "actual_failure_types": truth[card.event_id]["actual_failure_types"],
                      "teaching_point": point, "variant": None})

    # S10: 조치 후 재발. 같은 유형의 정탐 두 장이 24시간 안에 있으면, 앞의 것을
    # 1시간 뒤 조치 완료했다고 가정한다. 카드는 둘 다 실제다.
    hdf = [c for c in cards if p(c).predicted_failure_type == "HDF" and single(c)
           and truth[c.event_id]["case"] == "correct"]
    for a, b in zip(hdf, hdf[1:]):
        gap = datetime.fromisoformat(b.detected_at) - datetime.fromisoformat(a.detected_at)
        if timedelta(hours=2) < gap <= timedelta(hours=24):
            done = (datetime.fromisoformat(a.detected_at) + timedelta(hours=1)).isoformat()
            lines.append({"scenario_id": "S10", "card": b.model_dump(mode="json"),
                          "completed_repairs": [{"event_id": a.event_id, "failure_type": "HDF",
                                                 "completed_at": done}]})
            index.append({"scenario_id": "S10", "event_id": b.event_id,
                          "expected_route": "escalation", "expected_reasons": ["ESC-5"],
                          "truth_case": truth[b.event_id]["case"],
                          "actual_failure_types": truth[b.event_id]["actual_failure_types"],
                          "teaching_point": (f"조치 후 재발 — {a.event_id} 를 조치 완료(가정)한 뒤 "
                                             f"{(gap - timedelta(hours=1)).total_seconds() / 3600:.1f}시간 만에 같은 유형"),
                          "variant": "completed_repair_assumed"})
            break
    else:
        raise SystemExit("24시간 안의 HDF 정탐 쌍이 없습니다.")

    with (DATA / "eventcards" / "scenarios.jsonl").open("w", encoding="utf-8") as f:
        for line in lines:
            f.write(json.dumps(line, ensure_ascii=False) + "\n")
    (DATA / "eval" / "scenario_index.json").write_text(
        json.dumps(index, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    for item in index:
        print(f"{item['scenario_id']} {item['event_id']} {item['expected_route']:15} "
              f"{','.join(item['expected_reasons']) or '-':12} {item['truth_case']:12} {item['teaching_point']}")


if __name__ == "__main__":
    main()
