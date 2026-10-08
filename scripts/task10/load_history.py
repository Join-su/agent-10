"""정비 이력을 JSONL 원본에서 Postgres 표로 적재한다. 앱이 읽는 표다.

    docker compose up -d db
    uv run --env-file .env python scripts/task10/load_history.py

원본은 `task10_maintenance/data/history/maintenance_history.jsonl`(410건, scripts/task10/build_dataset.py
가 만든다)이다. 기록 하나를 `MaintenanceRecord` 계약으로 검증한 뒤 두 표로 펼친다.

    maintenance_record   기록 한 건 = 한 행. 센서 값은 열로 펼친다
    part_usage           기록에서 바꾼 부품. 한 기록에 여러 행

여러 번 돌려도 결과가 같다(표를 지우고 새로 만든다). **쓰기는 여기서만 한다.** 앱은 읽기
전용 세션으로만 붙는다.
"""
from __future__ import annotations

import json
import sys
from contextlib import closing
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2] / "task10_maintenance"
sys.path.insert(0, str(ROOT.parent))

from task10_maintenance import postgres  # noqa: E402
from task10_maintenance.domain import MaintenanceRecord  # noqa: E402

SOURCE = ROOT / "data" / "history" / "maintenance_history.jsonl"

# REAL 은 double precision 이어야 AVG 가 float 로 온다(numeric 이면 Decimal 이 와서 계산이 깨진다).
SCHEMA = {
    "maintenance_record": """
        record_id text PRIMARY KEY, equipment_id text, occurred_at text, record_type text,
        trigger text, past_alarm_type text, past_alarm_probability double precision, failure_types text,
        quality_grade text, air_temperature_k double precision, process_temperature_k double precision,
        rotational_speed_rpm double precision, torque_nm double precision, tool_wear_min double precision,
        temp_diff_k double precision, power_w double precision, symptom text, diagnosis text, action text,
        downtime_min bigint, outcome text, manual_refs text, technician text, source_row_id text""",
    "part_usage": "record_id text REFERENCES maintenance_record(record_id), part_no text, name text, qty bigint",
}


def rows(records: list[MaintenanceRecord]) -> tuple[list[tuple], list[tuple]]:
    """계약 객체를 표의 행으로 펼친다. 유형 목록은 쉼표 문자열, 매뉴얼 참조는 JSON 문자열."""
    record_rows, part_rows = [], []
    for r in records:
        s = r.sensor_snapshot
        record_rows.append((
            r.record_id, r.equipment_id, r.occurred_at, r.record_type, r.trigger,
            r.past_alarm.predicted_failure_type if r.past_alarm else None,
            r.past_alarm.probability if r.past_alarm else None, ",".join(r.failure_types),
            r.quality_grade, s.air_temperature_k, s.process_temperature_k, s.rotational_speed_rpm,
            s.torque_nm, s.tool_wear_min, s.temp_diff_k, s.power_w, r.symptom, r.diagnosis, r.action,
            r.downtime_min, r.outcome, json.dumps(r.manual_refs, ensure_ascii=False), r.technician,
            r.source["row_id"]))
        part_rows += [(r.record_id, p.part_no, p.name, p.qty) for p in r.parts_replaced]
    return record_rows, part_rows


def main() -> None:
    records = [MaintenanceRecord.model_validate_json(line)
               for line in SOURCE.read_text(encoding="utf-8").splitlines() if line.strip()]
    record_rows, part_rows = rows(records)
    with closing(postgres.connect(read_only=False)) as db:
        db.execute("DROP TABLE IF EXISTS part_usage")            # 참조하는 표부터 지운다
        db.execute("DROP TABLE IF EXISTS maintenance_record")
        for table, columns in SCHEMA.items():
            db.execute(f"CREATE TABLE {table} ({columns})")
        with db.cursor() as cursor:
            cursor.executemany("INSERT INTO maintenance_record VALUES (" + ", ".join(["%s"] * 24) + ")",
                               record_rows)
            cursor.executemany("INSERT INTO part_usage VALUES (%s, %s, %s, %s)", part_rows)
        db.execute("CREATE INDEX ON maintenance_record (record_type, occurred_at)")
        db.execute("CREATE INDEX ON part_usage (record_id)")
        db.commit()
    print(f"정비 이력 {len(record_rows)}건 · 교체 부품 {len(part_rows)}행 → Postgres ({SOURCE.name} 에서)")


if __name__ == "__main__":
    main()
