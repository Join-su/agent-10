"""라이브러리가 주는 것을 다시 만들지 않는다.

한 번 `completed_concepts` 를 "등장 금지"로 잘못 읽어, LangChain·LangGraph 가
주는 것을 전부 손으로 구현한 적이 있다. 학습자는 개념은 배우지만 실무에서 쓸
이름을 배우지 못한다. STEP 03~06 재편에서 **여덟 군데를 전부 치웠다.**

이 파일은 그때 쓴 xfail 스캐폴드를 대신한다. 스캐폴드는 "아직 남아 있다"를
표시하는 것이었고 할 일이 끝나면 지우기로 했다. 지우기만 하면 다음에 같은 일이
생겨도 아무도 막지 않으므로, **되돌아오지 못하게 하는 검사**를 대신 둔다.
"""
from __future__ import annotations

import ast
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
CONTRACTS = yaml.safe_load((ROOT / "notebook_contracts.yaml").read_text(encoding="utf-8"))
RETIRED = CONTRACTS["retired_reimplementations"]

# 앱 코드만 본다. Test 와 생성기에는 이름이 설명으로 등장할 수 있다.
SOURCE_DIRS = ("shared", "task10_maintenance")


def _implementation_files():
    for name in SOURCE_DIRS:
        for path in sorted((ROOT / name).rglob("*.py")):
            if "tests" not in path.parts:
                yield path


def _defined_names(source: str) -> set[str]:
    """**정의된** 이름만 센다. 주석이나 문자열에 적힌 같은 글자는 세지 않는다.

    한때 소스 문자열로 검사해서 docstring 에 이름만 적어도 통과한 적이 있다.
    """
    names: set[str] = set()
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            names.add(node.name)
        elif isinstance(node, ast.Assign):
            names |= {t.id for t in node.targets if isinstance(t, ast.Name)}
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            names.add(node.target.id)
    return names


def test_the_record_is_not_empty():
    """목록이 비면 이 파일의 모든 검사가 아무것도 보지 않는다."""
    assert len(RETIRED) >= 8, f"{len(RETIRED)}건만 기록되어 있다"
    for entry in RETIRED:
        assert entry["symbols"], entry["what"]
        assert entry["use"], entry["what"]


def test_no_retired_implementation_came_back():
    """치운 수제 구현이 다시 정의되면 여기서 멈춘다."""
    retired = {symbol: entry["use"] for entry in RETIRED for symbol in entry["symbols"]}

    offenders = []
    for path in _implementation_files():
        defined = _defined_names(path.read_text(encoding="utf-8"))
        for symbol in defined & set(retired):
            offenders.append(f"{path.relative_to(ROOT)}: {symbol} → {retired[symbol]} 를 쓴다")
    assert offenders == [], offenders


@pytest.mark.parametrize("entry", RETIRED, ids=lambda e: e["what"])
def test_every_recommended_replacement_can_actually_be_imported(entry):
    """권하는 이름이 설치된 버전에서 실제로 import 되는지 본다.

    문서를 보고 적으면 틀린다. LangChain 1.x 에서 리트리버 계열이 옮겨 갔고,
    `create_react_agent` 는 LangGraph v1.0 에서 `langchain.agents` 로 옮겨 갔다.
    """
    import importlib

    path = entry["use"].split(" ")[0]          # "패키지.이름 (설명)" 형태를 허용한다
    module_path, _, name = path.rpartition(".")
    module = importlib.import_module(module_path)
    assert hasattr(module, name), f"{module_path} 에 {name} 이 없다"
