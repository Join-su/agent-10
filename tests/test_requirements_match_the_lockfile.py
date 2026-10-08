"""requirements 파일은 uv.lock 에서 생성한 것이어야 한다.

정본은 `uv.lock` 이다. `requirements.txt` 를 손으로 고칠 수 있게 두면 정본이
둘이 되고, 둘은 반드시 갈라진다. 갈라진 뒤에는 "설치했는데 왜 안 되지"가 된다.
버전이 어긋나거나 잠긴 패키지가 빠지면 여기서 멈춘다.
"""
from __future__ import annotations

import re
import tomllib
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
RUNTIME = ROOT / "requirements.txt"
DEV = ROOT / "requirements-dev.txt"


def _pinned(path: Path) -> dict[str, str]:
    """`이름==버전` 줄만 읽는다. 주석과 환경 표시자는 버린다."""
    found: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line or line.startswith((" ", "#")):
            continue
        match = re.match(r"^([A-Za-z0-9._-]+)==([^\s;]+)", line)
        if match:
            found[match.group(1).lower().replace("_", "-")] = match.group(2)
    return found


def _locked() -> dict[str, str]:
    lock = tomllib.loads((ROOT / "uv.lock").read_text(encoding="utf-8"))
    return {
        package["name"].lower().replace("_", "-"): package["version"]
        for package in lock["package"]
        if "version" in package
    }


@pytest.mark.parametrize("path", [RUNTIME, DEV], ids=["requirements", "requirements-dev"])
def test_the_file_exists_and_pins_every_package(path):
    assert path.is_file(), f"{path.name} 이 없다"
    pinned = _pinned(path)
    assert len(pinned) >= 90, (
        f"{path.name} 에서 {len(pinned)}개만 읽었다. 형식이 바뀌었다면 이 검사가 "
        "거의 아무것도 보지 않는다."
    )
    # 다시 만드는 방법이 파일 안에 있어야 한다. 없으면 다음 사람이 손으로 고친다.
    header = path.read_text(encoding="utf-8")
    assert "uv export" in header, f"{path.name} 에 다시 만드는 명령이 없다"
    assert "uv.lock" in header, f"{path.name} 에 정본이 무엇인지 적혀 있지 않다"


@pytest.mark.parametrize("path", [RUNTIME, DEV], ids=["requirements", "requirements-dev"])
def test_every_pinned_version_matches_the_lockfile(path):
    locked = _locked()
    assert locked, "uv.lock 을 읽지 못했다"

    drifted = []
    unknown = []
    for name, version in _pinned(path).items():
        if name not in locked:
            unknown.append(name)
        elif locked[name] != version:
            drifted.append(f"{name}: 파일 {version} / lock {locked[name]}")

    assert not unknown, (
        f"{path.name} 에 uv.lock 에 없는 패키지가 있다: {unknown}. "
        "손으로 더했다면 pyproject.toml 을 고치고 uv lock 을 다시 돌려야 한다."
    )
    assert not drifted, (
        f"{path.name} 이 uv.lock 과 어긋난다: {drifted}. uv export 로 다시 만든다."
    )


def test_the_runtime_file_does_not_carry_test_tooling():
    """실행에 필요 없는 것을 넣으면 배포 이미지가 그만큼 커진다."""
    runtime = _pinned(RUNTIME)
    assert "pytest" not in runtime, "requirements.txt 에 pytest 가 들어갔다"
    assert "pytest" in _pinned(DEV), "requirements-dev.txt 에 pytest 가 없다"


def test_the_dev_file_is_a_superset_of_the_runtime_file():
    """개발 환경으로 설치하면 실행에 필요한 것이 전부 들어와야 한다."""
    runtime, dev = _pinned(RUNTIME), _pinned(DEV)
    missing = sorted(set(runtime) - set(dev))
    assert not missing, f"requirements-dev.txt 에 빠진 실행 의존성: {missing}"


def test_everything_the_app_imports_is_pinned():
    """App 이 실제로 import 하는 서드파티가 목록에 있어야 한다."""
    runtime = _pinned(RUNTIME)
    required = {
        "fastapi", "uvicorn", "streamlit", "pydantic", "pyyaml", "python-dotenv",
        "langchain-core", "langchain-text-splitters", "langchain-openai",
        "langchain-postgres", "langgraph", "langgraph-checkpoint",
        "mcp", "rank-bm25", "psycopg",
    }
    missing = sorted(required - set(runtime))
    assert not missing, f"requirements.txt 에 없는 필수 패키지: {missing}"
