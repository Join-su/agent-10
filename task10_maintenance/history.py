"""MC-01 정비 이력을 조회한다(SOP-EA-01 5.2).

이력은 숫자 위주의 기록이라 벡터 검색이 아니라 SQL 조건과 센서 거리로 찾는다.
**이벤트 시각보다 뒤의 기록은 절대 돌려주지 않는다.** 미래 기록을 근거로 쓰면
평가가 부풀고, 현장에서는 있을 수 없는 근거가 된다.

함수 하나가 근거 하나를 찾는다. `tools.py` 가 이 함수들을 그대로 Tool 로 연다.

조회마다 읽기 전용 연결을 새로 열고 닫는다. Agent 가 Tool 을 병렬로 부르면 조회가
서로 다른 스레드에서 돈다. 연결 하나를 나눠 쓰면 sqlite3 가 거부한다(실제로 났다).

저장소는 둘 중 하나다(`HISTORY_BACKEND`). 질의는 같고 연결만 다르다.

    sqlite    data/history/history.sqlite 를 mode=ro 로 연다 (기본)
    postgres  DATABASE_URL 의 같은 표를 읽기 전용 세션으로 연다 (scripts/task10/load_history.py 로 적재)
"""
from __future__ import annotations

import json
import sqlite3
from contextlib import closing
from functools import lru_cache
from pathlib import Path

from task10_maintenance import postgres
from task10_maintenance.domain import EvidenceItem, SensorSnapshot

DEFAULT_DB = Path(__file__).resolve().parent / "data" / "history" / "history.sqlite"
SENSORS = ["air_temperature_k", "process_temperature_k", "rotational_speed_rpm",
           "torque_nm", "tool_wear_min"]


class HistoryStore:
    backend = "sqlite"

    def __init__(self, path: Path | str = DEFAULT_DB):
        self.path = Path(path)
        if not self.path.exists():
            raise FileNotFoundError(
                f"정비 이력 DB 가 없습니다: {self.path}. "
                "uv run python scripts/task10/build_dataset.py 로 만드세요.")
        self._measure_scale()

    def _measure_scale(self) -> None:
        # 센서 거리는 표준화해서 잰다. 회전수(천 단위)가 온도(수백)를 덮지 않게.
        stats = self._scalar_row(
            "SELECT " + ", ".join(f"AVG({s}) AS m{i}, AVG({s}*{s}) AS q{i}" for i, s in enumerate(SENSORS))
            + " FROM maintenance_record")
        self.scale = {s: max((stats[2 * i + 1] - stats[2 * i] ** 2) ** 0.5, 1e-9)
                      for i, s in enumerate(SENSORS)}

    # --- 연결 -------------------------------------------------------------------

    def _connect(self):
        db = sqlite3.connect(f"file:{self.path}?mode=ro", uri=True)
        db.row_factory = sqlite3.Row
        return db

    def _sql(self, sql: str) -> str:
        """질의는 `?` 자리표시로 쓴다. 저장소가 다른 표기를 쓰면 여기서 바꾼다."""
        return sql

    def _scalar_row(self, sql: str, params: tuple = ()) -> tuple:
        with closing(self._connect()) as db:
            row = db.execute(self._sql(sql), params).fetchone()
        return tuple(row.values()) if isinstance(row, dict) else tuple(row)

    def _records(self, sql: str, params: tuple) -> list[dict]:
        """기록과 그 기록에서 바꾼 부품을 같은 연결 안에서 읽어 온다."""
        with closing(self._connect()) as db:
            rows = [dict(r) for r in db.execute(self._sql(sql), params).fetchall()]
            for row in rows:
                row["parts"] = [dict(p)["part_no"] for p in db.execute(
                    self._sql("SELECT part_no FROM part_usage WHERE record_id = ?"), (row["record_id"],))]
        return rows

    # --- 근거 하나씩 --------------------------------------------------------------

    def same_type_recent(self, failure_type: str, before: str, limit: int = 3) -> list[EvidenceItem]:
        """같은 유형으로 수리한 최근 기록. 그때 무엇을 했고 얼마나 걸렸는지."""
        rows = self._records(
            "SELECT * FROM maintenance_record WHERE record_type = 'failure_repair' "
            "AND (',' || failure_types || ',') LIKE ? AND occurred_at < ? "
            "ORDER BY occurred_at DESC LIMIT ?", (f"%,{failure_type},%", before, limit))
        return [self._item(r, f"같은 유형({failure_type}) 최근 수리 기록") for r in rows]

    def nearest(self, snapshot: SensorSnapshot, grade: str, before: str,
                limit: int = 3) -> list[EvidenceItem]:
        """같은 품질 등급에서 센서 값이 가장 가까운 기록. 유형을 미리 정하지 않는다."""
        rows = self._records(
            "SELECT * FROM maintenance_record WHERE quality_grade = ? AND occurred_at < ? "
            "AND record_type != 'tool_change'", (grade, before))
        target = snapshot.model_dump()

        def distance(row: dict) -> float:
            return sum(((row[s] - target[s]) / self.scale[s]) ** 2 for s in SENSORS) ** 0.5

        ranked = sorted(rows, key=distance)[:limit]
        return [self._item(r, f"센서 값이 가까운 기록(거리 {distance(r):.2f})") for r in ranked]

    def past_false_alarms(self, predicted_type: str, before: str,
                          limit: int = 2) -> list[EvidenceItem]:
        """같은 예측 유형으로 점검했는데 고장이 아니었던 기록(SOP-EA-01 8)."""
        rows = self._records(
            "SELECT * FROM maintenance_record WHERE record_type = 'false_alarm_check' "
            "AND past_alarm_type = ? AND occurred_at < ? ORDER BY occurred_at DESC LIMIT ?",
            (predicted_type, before, limit))
        return [self._item(r, f"같은 예측({predicted_type})의 과거 오탐 점검") for r in rows]

    def false_alarm_count(self, predicted_type: str, before: str) -> int:
        return self._scalar_row(
            "SELECT COUNT(*) FROM maintenance_record WHERE record_type = 'false_alarm_check' "
            "AND past_alarm_type = ? AND occurred_at < ?", (predicted_type, before))[0]

    def last_tool_change(self, before: str) -> list[EvidenceItem]:
        """마지막으로 공구를 바꾼 기록. 공구 교체를 겸한 수리(TWF·OSF)도 포함한다."""
        rows = self._records(
            "SELECT * FROM maintenance_record r WHERE occurred_at < ? AND ("
            "record_type = 'tool_change' OR EXISTS (SELECT 1 FROM part_usage p "
            "WHERE p.record_id = r.record_id AND p.part_no = 'PN-TL-1008')) "
            "ORDER BY occurred_at DESC LIMIT 1", (before,))
        return [self._item(r, "마지막 공구 교체") for r in rows]

    def gather(self, snapshot: SensorSnapshot, grade: str, predicted_type: str,
               before: str) -> list[EvidenceItem]:
        """SOP-EA-01 5.2 의 순서대로 모은다. 같은 기록은 한 번만 넣는다."""
        found: list[EvidenceItem] = []
        for items in (self.same_type_recent(predicted_type, before),
                      self.nearest(snapshot, grade, before),
                      self.past_false_alarms(predicted_type, before),
                      self.last_tool_change(before)):
            for item in items:
                if all(item.evidence_id != f.evidence_id for f in found):
                    found.append(item)
        return found

    @staticmethod
    def _item(row: dict, reason: str) -> EvidenceItem:
        used = ", ".join(row["parts"]) or "없음"
        refs = ", ".join(json.loads(row["manual_refs"]))
        excerpt = (f"[{row['occurred_at'][:16]}] {row['record_type']} {row['failure_types'] or '-'} | "
                   f"진단: {row['diagnosis']} | 조치: {row['action']} | 교체 부품: {used} | "
                   f"정지 {row['downtime_min']}분 | 결과: {row['outcome']} | 참조: {refs}")
        return EvidenceItem(evidence_id=row["record_id"], kind="history", reason=reason,
                            excerpt=excerpt)


class PostgresHistoryStore(HistoryStore):
    """같은 표를 Postgres 에서 읽는다. 질의는 그대로이고 자리표시만 `%s` 다."""

    backend = "postgres"

    def __init__(self):
        self.path = None
        try:
            self._measure_scale()
        except postgres.PostgresUnavailable:
            raise
        except Exception as error:          # 표가 없으면 적재 전이다
            raise postgres.PostgresUnavailable(
                f"Postgres 에 정비 이력이 없습니다({type(error).__name__}). 먼저 적재하세요: "
                f"{postgres.LOAD_COMMANDS[1]}") from error

    def _connect(self):
        return postgres.connect(read_only=True)

    def _sql(self, sql: str) -> str:
        return sql.replace("?", "%s")


@lru_cache(maxsize=4)
def _store(backend: str, url: str) -> HistoryStore:
    return PostgresHistoryStore() if backend == "postgres" else HistoryStore()


def history_store() -> HistoryStore:
    """설정(`HISTORY_BACKEND`)에 맞는 이력 저장소. 설정마다 한 번만 만든다."""
    backend = postgres.history_backend()
    if backend not in ("sqlite", "postgres"):
        raise postgres.PostgresUnavailable(f"HISTORY_BACKEND 는 sqlite 또는 postgres 여야 합니다. 받은 값: {backend!r}")
    return _store(backend, postgres.database_url() if backend == "postgres" else "")
