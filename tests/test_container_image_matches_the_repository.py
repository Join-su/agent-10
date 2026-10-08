"""이미지가 저장소와 어긋나지 않는지.

`Dockerfile` 은 Test 가 한 번도 보지 않던 파일이었다. STEP 재편으로 폴더가 전부
바뀌었는데 `COPY w1_retrieval_quality ./...` 가 그대로 남아 있었다. 전체 Test 가
초록인 채로 **`docker compose up --build` 만 깨지는** 상태였다.

컨테이너를 실제로 빌드하지 않고도 확인할 수 있는 것을 확인한다. 빌드는 느리고
CI 에서 늘 돌리기 어렵지만, "복사 대상이 실재하는가"와 "현행 앱이 전부 들어가는가"
는 파일만 읽어도 알 수 있다.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
DOCKERFILE = ROOT / "Dockerfile"


def _copied_sources() -> list[str]:
    """`COPY a b ./dst` 에서 목적지를 뺀 원본들."""
    sources: list[str] = []
    for line in DOCKERFILE.read_text(encoding="utf-8").splitlines():
        match = re.match(r"^COPY\s+(.+)$", line.strip())
        if not match:
            continue
        parts = match.group(1).split()
        sources += parts[:-1]          # 마지막은 목적지다
    return sources


@pytest.fixture(scope="module")
def current_projects() -> list[str]:
    manifest = yaml.safe_load((ROOT / "curriculum_manifest.yaml").read_text(encoding="utf-8"))
    return [p["id"] for p in manifest["projects"] if p.get("status", "current") == "current"]


def test_every_copied_path_exists():
    sources = _copied_sources()
    assert len(sources) >= 8, f"COPY 를 {len(sources)}개만 찾았다. 형식이 바뀌었다면 이 검사가 헐거워진다"
    missing = [s for s in sources if not (ROOT / s).exists()]
    assert missing == [], f"Dockerfile 이 없는 경로를 복사한다: {missing}"


def test_every_current_project_goes_into_the_image(current_projects):
    sources = set(_copied_sources())
    assert current_projects, "정본에 현행 프로젝트가 없다"
    missing = [p for p in current_projects if p not in sources]
    assert missing == [], f"이미지에 안 들어가는 현행 앱이 있다: {missing}"
    assert "shared" in sources, "shared 가 이미지에 없다"


def test_the_default_command_names_an_app_that_exists(current_projects):
    text = DOCKERFILE.read_text(encoding="utf-8")
    module = re.search(r'CMD \["uvicorn", "([\w.]+):app"', text)
    assert module, "CMD 가 uvicorn 으로 앱을 띄우지 않는다"
    assert module.group(1).split(".")[0] in current_projects, module.group(1)


def test_the_exposed_ports_match_the_compose_file():
    """문서와 compose 가 같은 포트를 말해야 한다. 한때 8021~8023 이 남아 있었다."""
    exposed = set(re.search(r"^EXPOSE (.+)$", DOCKERFILE.read_text(encoding="utf-8"),
                            re.M).group(1).split())
    compose = yaml.safe_load((ROOT / "compose.yml").read_text(encoding="utf-8"))
    # 이 저장소의 이미지로 도는 서비스만 본다. db 는 공개 Postgres 이미지라 그 이미지가 포트를 연다.
    published = {
        entry.split(":")[-1]
        for service in compose["services"].values() if "build" in service
        for entry in (service.get("ports") or [])
    }
    assert published, "compose 가 내보내는 포트가 없다"
    assert published <= exposed, f"compose 가 내보내는데 이미지가 열지 않는 포트: {published - exposed}"
