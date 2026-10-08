"""Notebook 내부가 계약을 지키는지. 파일 존재가 아니라 내용과 실행을 본다."""
from __future__ import annotations

import ast
import io
import json
import tokenize
from pathlib import Path

import pytest


def _notebooks(root: Path):
    return sorted(root.glob("*/notebooks/*.ipynb"))


def _parts(path: Path):
    payload = json.loads(path.read_text(encoding="utf-8"))
    markdown = [c for c in payload["cells"] if c["cell_type"] == "markdown"]
    code = [c for c in payload["cells"] if c["cell_type"] == "code"]
    prose = "\n".join("".join(c["source"]) for c in markdown)
    source = "\n".join("".join(c["source"]) for c in code)
    return prose, source, markdown, code


@pytest.fixture(scope="module")
def notebooks(root):
    found = _notebooks(root)
    assert found, "검사할 Notebook이 없다"
    return found


def test_every_notebook_is_valid_nbformat_4(notebooks):
    for path in notebooks:
        payload = json.loads(path.read_text(encoding="utf-8"))
        assert payload["nbformat"] == 4, path.name


def test_required_headings_are_present(notebooks, contracts):
    common = contracts["common"]
    for path in notebooks:
        prose = _parts(path)[0]
        for heading in common["required_headings"]:
            assert heading in prose, (path.name, heading)
        assert common["required_closing"] in prose, path.name


def test_cell_counts_meet_the_minimum(notebooks, contracts):
    common = contracts["common"]
    for path in notebooks:
        _, _, markdown, code = _parts(path)
        assert len(markdown) >= common["min_markdown_cells"], path.name
        assert len(code) >= common["min_code_cells"], path.name


def test_no_notebook_imports_or_calls_the_finished_app(notebooks, contracts):
    """문자열과 AST 두 겹으로 막는다. Notebook은 App을 쓰는 데모가 아니다."""
    common = contracts["common"]
    for path in notebooks:
        source = _parts(path)[1]
        for banned in common["forbidden_imports"]:
            assert f"import {banned}" not in source, (path.name, banned)
            assert f"from {banned}" not in source, (path.name, banned)

        tree = ast.parse(source)
        called = {
            node.func.id for node in ast.walk(tree)
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
        }
        assert called.isdisjoint(set(common["forbidden_calls"])), path.name


def test_every_notebook_asserts_and_uses_agreed_fixture_names(notebooks, contracts):
    prefixes = tuple(contracts["common"]["fixture_prefixes"]) + ("evaluation_cases", "failure_cases")
    for path in notebooks:
        source = _parts(path)[1]
        assert "assert " in source, path.name
        assert any(p in source for p in prefixes), path.name


def test_code_cells_carry_their_own_comments(notebooks):
    """셀마다 최소 2개, 그리고 상투 주석 복붙을 막기 위해 고유율 70% 이상."""
    for path in notebooks:
        comments: list[str] = []
        for cell in _parts(path)[3]:
            text = "".join(cell["source"])
            found = [
                token.string
                for token in tokenize.generate_tokens(io.StringIO(text).readline)
                if token.type == tokenize.COMMENT
            ]
            assert len(found) >= 2, (path.name, found)
            comments.extend(found)
        assert len(set(comments)) >= int(len(comments) * 0.7), path.name


def test_contract_primitives_actually_appear_in_the_notebook(notebooks, contracts):
    by_file = {n["file"]: n for n in contracts["notebooks"]}
    for path in notebooks:
        contract = by_file[path.name]
        source = _parts(path)[1]
        missing = [p for p in contract["primitives"] if p not in source]
        assert missing == [], (path.name, missing)


def test_every_notebook_runs_top_to_bottom(notebooks):
    """파일이 유효한 것과 실행되는 것은 다르다. 셀을 순서대로 실행한다."""
    for path in notebooks:
        namespace: dict = {}
        payload = json.loads(path.read_text(encoding="utf-8"))
        for cell in payload["cells"]:
            if cell["cell_type"] != "code":
                continue
            body = "".join(cell["source"])
            try:
                # dont_inherit: 이 Test 파일의 `from __future__ import annotations` 가
                # 셀에 옮겨붙지 않게 한다. 붙으면 annotation 이 문자열이 되어
                # `TypedDict` 를 나중에 해석할 때 셀에서 import 한 이름을 못 찾는다.
                # Jupyter 도 그 future 를 물려주지 않으므로 이쪽이 실제와 같다.
                exec(compile(body, f"{path.name}:{cell.get('id', '?')}", "exec",
                             dont_inherit=True), namespace)
            except Exception as error:  # noqa: BLE001 - 어떤 실패든 Notebook 결함이다
                pytest.fail(f"{path.name} 실행 실패: {type(error).__name__}: {error}")


# Notebook 생성기는 검사 대상 링크 문자열을 그대로 담고 있다. 근거 출처에 넣으면
# 구현에서 심볼을 지워도 생성기에 남은 글자가 검사를 통과시킨다. 2차 수정에서
# 오탐을 없애려고 저장소 전체로 넓혔다가 검사를 무력화했다.
SYMBOL_SOURCE_EXCLUDES = ("scripts", ".venv", "notebooks")


def _implementation_files(root):
    for path in sorted(root.rglob("*.py")):
        if not set(path.parts) & set(SYMBOL_SOURCE_EXCLUDES):
            yield path


def _defined_names(source: str) -> set[str]:
    """모듈이 정의하는 이름. 주석·문자열에 적힌 같은 글자는 제외된다."""
    names: set[str] = set()
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            names.add(node.name)
        elif isinstance(node, ast.Assign):
            names |= {t.id for t in node.targets if isinstance(t, ast.Name)}
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            names.add(node.target.id)
    return names


def _symbol_name(symbol: str) -> str:
    return symbol.split("::")[-1].split(".")[-1].rstrip("()")


def _named_symbols(text: str) -> list[str]:
    import re

    return [s for s in re.findall(r"`([A-Za-z_][A-Za-z0-9_.:/]*)`", text)]


def _resolve(symbol: str, root, project_id: str) -> str | None:
    """해석하지 못하면 이유를 돌려준다. 해석되면 None.

    `module.py::name` 형식은 **엄격하게** 본다. 그 모듈이 실재해야 하고 그 안에
    이름이 정의되어 있어야 한다. `_is_grounded` → `_grounded_hits` 로 바뀌면서
    깨진 것이 정확히 이 형식이었다.
    """
    if "::" in symbol:
        module, _, name = symbol.partition("::")
        # 누적 구조에서는 app_link 가 shared/ 를 가리키는 것이 정상이다.
        # STEP 06 의 그래프가 STEP 04 의 리트리버를 부르는 것이 그 예다.
        path = root / module if module.startswith("shared/") else root / project_id / module
        if not path.is_file():
            return f"모듈 없음: {module}"
        if _symbol_name(name) not in _defined_names(path.read_text(encoding="utf-8")):
            return f"{module} 에 {name} 이 정의되지 않음"
        return None

    if "://" in symbol:
        # MCP 리소스 URI 는 파일이 아니다. 서버가 선언했는지로 본다.
        text = "\n".join(f.read_text(encoding="utf-8") for f in _implementation_files(root))
        return None if symbol in text else f"선언되지 않은 리소스: {symbol}"

    if "/" in symbol or symbol.endswith((".py", ".yaml", ".yml", ".md")):
        if (root / project_id / symbol).exists() or (root / symbol).exists():
            return None
        return f"경로 없음: {symbol}"

    # 맨 이름. 구현·Test 어디든 쓰이면 된다. 생성기는 제외한 뒤 본다.
    text = "\n".join(p.read_text(encoding="utf-8") for p in _implementation_files(root))
    return None if _symbol_name(symbol) in text else f"이름 없음: {symbol}"


def test_notebook_app_links_name_symbols_that_exist(root):
    """Notebook 이 "App 의 이 함수로 확장된다" 고 적었으면 그 함수가 있어야 한다.

    Phase 5 에서 한 번 확인했지만 Test 가 아니어서, 그 뒤 `_is_grounded` 를
    `_grounded_hits` 로 바꾸면서 조용히 깨졌다. 일회성 확인은 드리프트를 막지
    못한다.
    """
    import json

    broken: list[str] = []
    strict = 0
    for path in sorted(root.glob("*/notebooks/*.ipynb")):
        project_id = path.parts[-3]
        payload = json.loads(path.read_text(encoding="utf-8"))
        prose = "\n".join(
            "".join(cell["source"]) for cell in payload["cells"]
            if cell["cell_type"] == "markdown"
        )
        section = prose.split("## 실제 app 연결")[-1].split("##")[0]
        for symbol in _named_symbols(section):
            if "::" in symbol:
                strict += 1
            reason = _resolve(symbol, root, project_id)
            if reason:
                broken.append(f"{path.name} → {symbol} ({reason})")

    assert broken == [], broken
    # 엄격 해석 대상이 줄면 검사가 조용히 헐거워진다. 집계 하한보다 이쪽이 잘 묶인다.
    assert strict >= 18, f"module::name 형식이 {strict}개뿐이다. 검사가 헐거워졌다"


def test_every_notebook_matches_what_the_generator_writes(notebooks, root):
    """Notebook 은 생성기가 쓴 그대로여야 한다.

    한때 생성기가 spec 파일 7개 중 하나만 불렀다. 나머지 24개는 손으로 고칠 수
    있었고, "생성기와 Notebook 이 일치한다"는 확인이 그 24개에 대해 아무것도
    검사하지 않았다. 생성기가 안 쓰는 파일은 diff 가 언제나 같기 때문이다.

    **내용만 본다. 실행 결과는 보지 않는다.** 학습자가 Notebook 을 돌리고 저장하면
    `outputs` 와 `execution_count` 가 채워진다. 그것까지 어긋남으로 세면 공부한
    사람을 "손으로 고쳤다"고 하는 셈이다. 실제로 6개가 그렇게 잡혔다.
    """
    import json
    import sys

    sys.path.insert(0, str(root / "scripts"))
    try:
        import build_notebooks

        specs = build_notebooks.all_specs()
        rendered = {
            f"{spec['project']}/{spec['file']}": _content(build_notebooks.build(spec))
            for spec in specs
        }
    finally:
        sys.path.pop(0)
    assert len(specs) == len(notebooks), (
        f"생성기가 아는 Notebook 이 {len(specs)}개인데 디스크에는 {len(notebooks)}개다. "
        "spec 파일을 SPEC_MODULES 에 넣지 않았다."
    )

    drifted = [
        key for key, expected in rendered.items()
        if _content(json.loads(
            (root / key.replace("/", "/notebooks/", 1)).read_text(encoding="utf-8"))) != expected
    ]
    assert not drifted, (
        "손으로 고친 Notebook 이 있다. spec 을 고치고 다시 생성해야 한다: " + ", ".join(drifted)
    )


def _content(notebook: dict) -> list[tuple[str, str]]:
    """Notebook 의 내용만 뽑는다. 실행 결과와 실행 번호는 뺀다."""
    return [(cell["cell_type"], "".join(cell["source"])) for cell in notebook["cells"]]
