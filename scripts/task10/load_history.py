"""정비 이력을 SQLite 에서 Postgres 로 옮긴다. 앱이 HISTORY_BACKEND=postgres 일 때 읽는 표다.

    docker compose up -d db
    uv run --env-file .env python scripts/task10/load_history.py

정본은 `task10_maintenance/data/history/history.sqlite` 다(scripts/task10/build_dataset.py 가
만든다). 이 스크립트는 같은 두 표(maintenance_record, part_usage)를 Postgres 에 그대로
다시 만든다. 여러 번 돌려도 결과가 같다(표를 지우고 새로 만든다).

**쓰기는 여기서만 한다.** 앱은 읽기 전용 세션으로만 붙는다.
"""
from __future__ import annotations

import sqlite3
import sys
from contextlib import closing
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2] / "task10_maintenance"
sys.path.insert(0, str(ROOT.parent))

from task10_maintenance import postgres  # noqa: E402
from task10_maintenance.history import DEFAULT_DB  # noqa: E402

TABLES = ("maintenance_record", "part_usage")
# SQLite 의 선언 타입 → Postgres 타입. REAL 은 double precision 이어야 AVG 가 float 로 온다.
TYPES = {"TEXT": "text", "REAL": "double precision", "INTEGER": "bigint"}


def columns(source: sqlite3.Connection, table: str) -> list[tuple[str, str, bool]]:
    return [(row[1], TYPES[row[2].upper()], bool(row[5])) for row in source.execute(f"PRAGMA table_info({table})")]


def main() -> None:
    with closing(sqlite3.connect(f"file:{DEFAULT_DB}?mode=ro", uri=True)) as source, \
            closing(postgres.connect(read_only=False)) as target:
        for table in reversed(TABLES):                      # 참조하는 표부터 지운다
            target.execute(f"DROP TABLE IF EXISTS {table}")
        for table in TABLES:
            cols = columns(source, table)
            ddl = ", ".join(f"{name} {kind}" + (" PRIMARY KEY" if pk else "") for name, kind, pk in cols)
            target.execute(f"CREATE TABLE {table} ({ddl})")
            rows = source.execute(f"SELECT {', '.join(c[0] for c in cols)} FROM {table}").fetchall()
            marks = ", ".join(["%s"] * len(cols))
            with target.cursor() as cursor:
                cursor.executemany(f"INSERT INTO {table} VALUES ({marks})", rows)
            print(f"{table}: {len(rows)}행")
        target.execute("CREATE INDEX ON maintenance_record (record_type, occurred_at)")
        target.execute("CREATE INDEX ON part_usage (record_id)")
        target.commit()
    print("정비 이력을 Postgres 에 적재했습니다. 앱에서 쓰려면 .env 에 HISTORY_BACKEND=postgres")


if __name__ == "__main__":
    main()
