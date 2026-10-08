"""운영자에게 보여 주는 설정이 실제로 코드에 닿는지 확인한다.

`.env.example` 과 `compose.yml` 은 운영자가 읽고 값을 바꾸는 문서다. 거기 적힌
변수를 코드가 읽지 않으면, 운영자는 바꿨다고 믿는데 아무 일도 일어나지 않는다.
`RAG_RETRIEVAL_K=4` 가 정확히 그랬다. 코드는 `RETRIEVAL_K = 3` 을 쓰고 있었고,
평가셋이 선언한 값도 3 이라 광고된 4 는 죽었을 뿐 아니라 모순이었다.
"""
import re
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
SOURCE_DIRS = ("shared", "task10_maintenance", "app_pages")
# 컨테이너·도구가 쓰는 변수. 애플리케이션 코드가 읽지 않는 것이 정상이다.
NOT_READ_BY_APP = {
    "POSTGRES_PASSWORD",     # Postgres 컨테이너가 읽는다
    "POSTGRES_DB",           # Postgres 컨테이너가 읽는다
    "POSTGRES_USER",         # Postgres 컨테이너가 읽는다
}


def _advertised() -> dict[str, set[str]]:
    """운영자용 파일이 이름을 노출하는 환경 변수."""
    found: dict[str, set[str]] = {}
    example = ROOT / ".env.example"
    found[".env.example"] = {
        m.group(1)
        for m in re.finditer(r"^([A-Z][A-Z0-9_]*)=", example.read_text(encoding="utf-8"), re.M)
    }
    compose = yaml.safe_load((ROOT / "compose.yml").read_text(encoding="utf-8"))
    names: set[str] = set()
    for service in (compose.get("services") or {}).values():
        for key in (service.get("environment") or {}):
            names.add(key)
    found["compose.yml"] = names
    return found


def test_every_source_dir_actually_exists():
    """없는 폴더를 적어 두면 `rglob` 이 조용히 비어 그 앱을 아무도 보지 않는다.

    실제로 그랬다. 지워진 `w3_capa_control_tower` 가 목록에 남아 `s06_credit_review`
    가 한 번도 검사되지 않았다.
    """
    missing = [d for d in SOURCE_DIRS if not (ROOT / d).is_dir()]
    assert missing == [], missing
    assert len(SOURCE_DIRS) >= 3, f"검사 대상이 {len(SOURCE_DIRS)}개뿐이다"


def _read_by_code() -> set[str]:
    """코드가 이름을 아는 환경 변수.

    `os.getenv("NAME")` 만 찾으면 안 된다. 이름을 문자열로 헬퍼에 넘기는 경우가
    흔하고(`_live_threshold("RAG_MIN_RELEVANCE", ...)`, `("S03_API_URL", 기본값)`),
    그것도 엄연히 읽는 것이다. 따옴표 안의 이름을 센다 — 주석은 세지 않는다.
    """
    names: set[str] = set()
    files = [p for d in SOURCE_DIRS for p in (ROOT / d).rglob("*.py")]
    files += [ROOT / "streamlit_app.py"]
    for path in files:
        if not path.is_file():
            continue
        source = path.read_text(encoding="utf-8")
        names |= set(re.findall(r'["\']([A-Z][A-Z0-9_]{2,})["\']', source))
    return names


@pytest.mark.parametrize("source", [".env.example", "compose.yml"])
def test_every_advertised_setting_is_read_by_the_code(source):
    advertised = _advertised()[source] - NOT_READ_BY_APP
    dead = sorted(advertised - _read_by_code())
    assert not dead, (
        f"{source} 가 코드에서 읽지 않는 설정을 광고한다: {dead}. "
        "운영자는 바꿨다고 믿지만 아무 일도 일어나지 않는다. "
        "코드가 읽게 하거나 설정에서 지워야 한다."
    )


def test_the_retrieval_k_is_code_not_an_environment_variable():
    """검색 k 는 설정이 아니다. 질의마다 몇 개를 찾았는지 진단이 함께 말한다.

    환경 변수로 열면 같은 카드가 실행마다 다른 근거를 내도 이유를 알 수 없다.
    """
    assert "RAG_RETRIEVAL_K" not in _read_by_code(), (
        "검색 k 를 환경 변수로 열면 어느 k 에서 찾은 근거인지 응답만 보고 알 수 없다"
    )


def _published_db_port() -> str:
    import re

    compose = (ROOT / "compose.yml").read_text(encoding="utf-8")
    published = re.search(r'"127\.0\.0\.1:(\d+):5432"', compose)
    assert published, "compose.yml 의 db 포트 매핑을 읽지 못했다"
    return published.group(1)


def test_the_example_database_url_uses_the_port_the_compose_file_publishes():
    """`.env.example` 의 포트가 compose 의 db 가 내보내는 포트와 같아야 한다.

    `cp .env.example .env` → `docker compose up -d db` → 적재 스크립트 가 문서에 적힌
    순서다. 예시의 포트가 틀리면 그 순서를 그대로 따른 사람이 반드시 실패한다.
    v2 에서 실제로 5432 로 적혀 있었고 compose 는 5433 으로 내보내고 있었다.
    """
    import re

    port = _published_db_port()
    example = (ROOT / ".env.example").read_text(encoding="utf-8")
    host_url = re.search(r"^DATABASE_URL=(\S+)", example, re.M)
    assert host_url, ".env.example 에 DATABASE_URL 이 없다"
    assert f"127.0.0.1:{port}/" in host_url.group(1), (
        f"DATABASE_URL 이 127.0.0.1:{port} 를 가리키지 않는다: {host_url.group(1)}"
    )


def test_containers_reach_the_database_by_its_service_name():
    """컨테이너 안에서 127.0.0.1 은 자기 자신이다. compose 의 서비스 이름(db)으로 붙어야 한다.

    v2 에서는 DB 가 별도 compose 라 host.docker.internal 을 거쳐야 했고, 기본값이 빈
    문자열이라 컨테이너에서만 503 이 난 적이 있다. 여기서는 같은 compose 안에 두었다.
    """
    import re

    compose = (ROOT / "compose.yml").read_text(encoding="utf-8")
    values = re.findall(r"^\s*DATABASE_URL:\s*(.+)$", compose, re.M)
    assert len(values) >= 2, "init 과 task10 이 모두 DATABASE_URL 을 받아야 한다"
    for value in values:
        assert "@db:5432/" in value, f"컨테이너가 서비스 이름으로 DB 에 붙지 않는다: {value}"
        assert "127.0.0.1" not in value


def test_the_guidance_commands_work_on_windows_too():
    """오류가 안내하는 명령도 세 운영체제에서 동작해야 한다.

    한때 `APP_MODE=live uv run ...` 을 안내했는데 그 문법은 POSIX 전용이라
    Windows 에서 "APP_MODE는 내부 또는 외부 명령이 아닙니다" 가 났다.
    """
    import re

    source = (ROOT / "shared" / "rag" / "store.py").read_text(encoding="utf-8")
    commands = re.findall(r"([A-Za-z][^\"\n]*docker compose[^\"\n]*)", source)
    assert commands, "pgvector 안내에 실행할 명령이 없다"
    for command in commands:
        assert not re.match(r"[A-Z][A-Z0-9_]*=", command.strip()), (
            f"Windows 에서 쓸 수 없는 명령을 안내한다: {command}"
        )
