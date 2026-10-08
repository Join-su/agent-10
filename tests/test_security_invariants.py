"""주차를 가로지르는 안전 불변조건.

주차별 Test가 각자 확인하지만, 새 주차가 생겼을 때 이것을 빠뜨리면 아무도
잡아 주지 않는다. 여기서 모든 주차를 한 번에 훑는다.
"""
from __future__ import annotations

import re

import pytest

# 이 워크플로들은 검토만 한다. 실행 결과를 담는 필드는 항상 비어 있어야 한다.
NON_EXECUTION_FIELDS = ("executed_orders", "executed_actions")

SECRET_PATTERNS = (
    re.compile(r"sk-[A-Za-z0-9]{20,}"),
    re.compile(r"AKIA[0-9A-Z]{16}"),
    re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY"),
)


def _week_sources(manifest, root):
    for project in manifest["projects"]:
        for path in (root / project["id"]).rglob("*.py"):
            yield path, path.read_text(encoding="utf-8")


def test_no_source_file_contains_a_credential(manifest, root):
    for path, source in _week_sources(manifest, root):
        for pattern in SECRET_PATTERNS:
            assert not pattern.search(source), path.relative_to(root)


def test_the_env_example_never_holds_a_real_key(root):
    text = (root / ".env.example").read_text(encoding="utf-8")
    for pattern in SECRET_PATTERNS:
        assert not pattern.search(text)


def test_every_declared_safety_invariant_is_non_empty(manifest):
    assert manifest["safety_invariants"]
    for project in manifest["projects"]:
        assert project["safety_invariants"], project["id"]


def test_execution_fields_are_only_ever_assigned_an_empty_list(manifest, root):
    """`executed_* = [...]` 에 값이 들어가는 코드가 있으면 실패한다."""
    offenders = []
    for path, source in _week_sources(manifest, root):
        for field in NON_EXECUTION_FIELDS:
            for match in re.finditer(rf"{field}\s*=\s*(\[[^\]]*\])", source):
                if match.group(1).strip() != "[]":
                    offenders.append(f"{path.relative_to(root)}: {match.group(0)}")
    assert offenders == [], offenders


def test_no_week_shells_out_or_writes_to_an_external_system(manifest, root):
    """합성 데이터 읽기만 한다. subprocess·requests 쓰기 경로가 없어야 한다."""
    banned = ("subprocess.run", "subprocess.Popen", "os.system", "requests.post", "httpx.post")
    # 예외 없음. MCP 서버 Process 기동은 langchain_mcp_adapters 가 맡는다.
    allowed_files: set[str] = set()
    offenders = []
    for path, source in _week_sources(manifest, root):
        if path.name in allowed_files:
            continue
        offenders += [f"{path.relative_to(root)}: {b}" for b in banned if b in source]
    assert offenders == [], offenders


def test_every_response_model_that_can_execute_declares_the_empty_default(manifest, root):
    """비실행 필드는 기본값이 빈 목록이어야 한다. 빠뜨리면 None 이 새어 나간다."""
    found = 0
    for path, source in _week_sources(manifest, root):
        for field in NON_EXECUTION_FIELDS:
            if f"{field}: list[str]" in source:
                found += 1
                assert "default_factory=list" in source, path.relative_to(root)
    assert found >= 1, "비실행 필드를 선언한 앱이 없다"


# "읽기 전용"은 **업무 데이터** 에 대한 주장이다. 구매·승인·설비 변경을 하지
# 않는다는 뜻이지, 프로세스가 아무것도 저장하지 않는다는 뜻이 아니다.
#
# 쓰기가 허용된 두 종류:
#   적재 CLI — 운영자가 명시적으로 실행해 지식 문서를 벡터 DB 에 넣는다
#   Thread 저장소 — 워크플로 자신의 중단 상태를 보관한다. 이것이 없으면
#                   재시작 시 승인 대기 Thread 가 사라진다
WRITE_CALLS = ("add_documents", "init_vectorstore_table", "INSERT", "UPDATE", "DELETE", "DROP")
INGEST_MODULES = {"ingest.py", "live.py"}
STATE_MODULES = {"persistence.py"}
WRITER_MODULES = INGEST_MODULES | STATE_MODULES


def test_request_handling_paths_never_write(manifest, root):
    """app.py 와 그것이 부르는 워크플로에 쓰기 호출이 없어야 한다.

    쓰기는 운영자가 명시적으로 실행하는 적재 CLI 에만 있다. 요청 하나가
    데이터베이스를 바꾸면 "읽기 전용"이라는 문서가 거짓이 된다.
    """
    offenders = []
    for project in manifest["projects"]:
        for path in (root / project["id"]).rglob("*.py"):
            if path.name in WRITER_MODULES or "tests" in path.parts:
                continue
            source = path.read_text(encoding="utf-8")
            offenders += [f"{path.relative_to(root)}: {c}" for c in WRITE_CALLS if c in source]
    assert offenders == [], offenders


def test_only_the_declared_modules_write(manifest, root):
    """쓰기가 있는 모듈이 적재·상태 저장 두 종류에 한정되는지 확인한다."""
    writers = set()
    for project in manifest["projects"]:
        for path in (root / project["id"]).rglob("*.py"):
            if "tests" in path.parts:
                continue
            source = path.read_text(encoding="utf-8")
            if any(c in source for c in WRITE_CALLS):
                writers.add(path.name)
    assert writers <= WRITER_MODULES, f"예상 밖 쓰기 모듈: {writers - WRITER_MODULES}"


def test_no_application_code_writes_sql_at_all(root):
    """Thread 저장소가 업무 데이터에 손대지 않는 근거가 바뀌었다.

    한때 체크포인트 저장소를 직접 구현했고, 그때의 근거는 "자기 테이블만 쓴다"
    였다. 그 구현을 지우고 라이브러리(`AsyncSqliteSaver`)로 바꿨으므로 이제
    근거는 더 단순하다 — **우리 코드에 SQL 이 한 줄도 없다.**

    문자열 리터럴만 본다. 주석과 docstring 까지 훑으면 SQL 을 설명하는 문장이
    질의로 읽힌다. 실제로 한글 조사를 테이블 이름으로 잡은 적이 있다.
    """
    import ast
    import re

    statement = re.compile(
        r"\b(insert\s+into|update\s+\w+\s+set|delete\s+from|drop\s+table|"
        r"create\s+table|alter\s+table)\b", re.I)

    checked = 0
    offenders = []
    for source_dir in ("shared", "task10_maintenance"):
        for path in sorted((root / source_dir).rglob("*.py")):
            checked += 1
            tree = ast.parse(path.read_text(encoding="utf-8"))
            docstrings = {
                node.body[0].value
                for node in ast.walk(tree)
                if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef,
                                     ast.AsyncFunctionDef))
                and node.body and isinstance(node.body[0], ast.Expr)
                and isinstance(node.body[0].value, ast.Constant)
            }
            for node in ast.walk(tree):
                if (isinstance(node, ast.Constant) and isinstance(node.value, str)
                        and node not in docstrings and statement.search(node.value)):
                    offenders.append(f"{path.relative_to(root)}: {node.value[:60]}")
    assert offenders == [], offenders
    assert checked >= 20, f"{checked}개 파일만 봤다. 검사 범위가 좁아졌다"

def test_diagnostics_never_returns_any_part_of_a_key(manifest, root):
    """인증 없는 endpoint 가 키의 일부라도 돌려주면 안 된다."""
    for project in manifest["projects"]:
        for path in (root / project["id"]).rglob("*.py"):
            source = path.read_text(encoding="utf-8")
            assert "api_key[:" not in source, path.relative_to(root)
            assert "api_key_prefix" not in source, path.relative_to(root)
