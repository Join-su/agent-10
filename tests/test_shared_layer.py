"""`shared/` 가 실제로 공유되는지, 그리고 STEP 앱이 그것을 다시 만들지 않는지.

한때 MCP 전송 배관이 두 주차에 그대로 복제돼 있었다. 폴더만 만들어 두면 다음
사람도 같은 실수를 한다. **공유해야 할 것이 공유되는지 검사한다.**

`shared/` 는 STEP 을 지나며 자란다.

    shared/rag/    STEP 03·04 — 체인, 임베딩, 벡터스토어, 리트리버
    shared/tools/  STEP 05    — Tool 모델, Agent 루프, MCP 연결
    shared/graph/  STEP 06    — 그래프 저장소, 사람 승인 지점
"""
from __future__ import annotations

import ast
import asyncio
import pathlib

import pytest

SHARED_PACKAGES = ("rag", "tools", "graph")
MCP_PROJECTS = ("task10_maintenance",)


def _project_dirs(root) -> list[pathlib.Path]:
    return [root / "task10_maintenance"]


def _defined_names(source: str) -> set[str]:
    return {
        node.name
        for node in ast.walk(ast.parse(source))
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))
    }


def _sources(directory: pathlib.Path):
    for path in sorted(directory.rglob("*.py")):
        if "tests" not in path.parts and "notebooks" not in path.parts:
            yield path


def test_every_shared_package_exists_and_is_used(root):
    """폴더만 있고 아무도 안 쓰면 누적이 아니라 장식이다."""
    projects = _project_dirs(root)
    assert all(p.is_dir() for p in projects), [p.name for p in projects]

    for package in SHARED_PACKAGES:
        directory = root / "shared" / package
        assert directory.is_dir(), f"shared/{package} 가 없다"
        users = [
            project.name for project in projects
            if any(f"shared.{package}" in path.read_text(encoding="utf-8")
                   for path in _sources(project))
        ]
        assert users, f"shared/{package} 를 쓰는 앱이 없다"


def test_the_app_stands_on_all_three_layers(root):
    """누적이 문장이 아니라 코드인지 본다.

    과제 10 의 그래프는 매뉴얼 검색(`shared/rag`), 이력 Tool Agent(`shared/tools`),
    멈춤과 재개 저장소(`shared/graph`)를 실제로 부른다. 부르지 않으면 여기서 멈춘다.
    """
    source = "".join(path.read_text(encoding="utf-8")
                     for path in _sources(root / "task10_maintenance"))
    for package, why in (("shared.rag", "매뉴얼 근거를 찾는 리트리버"),
                         ("shared.tools", "정비 이력을 읽는 Tool Agent"),
                         ("shared.graph", "멈춤과 재개")):
        assert f"from {package}" in source, f"과제 10 이 {package} 를 쓰지 않는다 ({why})"


def test_no_project_redefines_what_shared_provides(root):
    """같은 이름을 앱 안에서 다시 정의하면 두 정본이 생긴다."""
    shared_names: set[str] = set()
    for package in SHARED_PACKAGES:
        for path in _sources(root / "shared" / package):
            shared_names |= {n for n in _defined_names(path.read_text(encoding="utf-8"))
                             if not n.startswith("_")}
    assert len(shared_names) >= 15, f"공유 이름을 {len(shared_names)}개만 모았다"

    offenders = []
    for project in _project_dirs(root):
        for path in _sources(project):
            clash = _defined_names(path.read_text(encoding="utf-8")) & shared_names
            offenders += [f"{path.relative_to(root)}: {name}" for name in sorted(clash)]
    assert offenders == [], offenders


# --- MCP 표면 ---------------------------------------------------------------

@pytest.mark.parametrize("project", MCP_PROJECTS)
def test_every_mcp_server_opens_exactly_the_read_only_tools(project):
    """MCP 로 나가는 표면을 **실제로 띄워서** 센다.

    소스 문자열을 세면 데코레이터 모양이 바뀐 순간 아무것도 세지 않는다.
    그런 검사가 통과하고 있던 적이 있다.

    업무 데이터가 두 번 바뀌지 않는 근거는 "쓰기 Tool 이 없다" 하나뿐이다.
    시간 초과 취소는 서버까지 가지 않는다. 요청이 이미 실렸으면 서버는 실행을
    마치고, 호출한 쪽이 재시도하면 같은 Tool 이 두 번 돈다.
    """
    import importlib

    from shared.tools import mcp_tools, stdio_server

    expected = set(importlib.import_module(f"{project}.tools").READ_ONLY_TOOLS)
    from task10_maintenance.loop import subprocess_loop

    opened = asyncio.run(mcp_tools({"probe": stdio_server(f"{project}.mcp_server")}), loop_factory=subprocess_loop)

    assert {t.name for t in opened} == expected, [t.name for t in opened]
    assert expected, f"{project} 가 Tool 을 하나도 선언하지 않았다"


@pytest.mark.parametrize("project", MCP_PROJECTS)
def test_the_mcp_client_uses_the_shared_connection(root, project):
    """붙는 법을 앱마다 다시 만들면 배관이 다시 복제된다."""
    source = "".join(path.read_text(encoding="utf-8")
                     for path in _sources(root / project))
    assert "mcp_tools" in source, f"{project} 이 shared.tools.mcp_tools 를 쓰지 않는다"
    assert "MultiServerMCPClient" not in source, (
        f"{project} 이 MCP 클라이언트를 직접 만든다. shared/tools/mcp.py 가 맡는다")
