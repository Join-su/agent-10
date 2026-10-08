"""선언한 Capability가 구현에 실제로 도달했는지.

**이 파일의 이전 버전은 스스로 과대표기였다.** 조건을 파일 전체의 부분 문자열
존재로 증명해, 주석이나 문자열 리터럴이나 죽은 코드에 이름만 있어도 통과했다.
막으려던 것을 스스로 저지른 것이다.

지금은 두 겹으로 본다.

1. **AST 기반** — 이름이 실제로 import·호출·정의·속성 접근으로 쓰이는지 본다.
   주석·docstring·문자열 안의 같은 글자는 세지 않는다. 테스트 파일은
   근거에서 제외한다. Test 가 구현을 대신 증명할 수는 없다.
2. **동작 기반** — Capability 마다 그것을 실행해 증명하는 Test 를 manifest 가
   지목하게 한다. 지목한 Test 는 자기 Project 소속이어야 하고, manifest 에
   등재되어야 하고, 실제로 실행해 통과해야 하고, 단언을 담아야 한다.

## 이 검사로 막지 못하는 것 — 독립 Review 3차(2026-09-21) 지적

**이 파일을 과신하지 말 것.** 아래는 알면서 막지 않은 구멍이며, 고치려면
"이 Test 가 진짜 증명인가" 를 기계가 판정해야 한다. 그 판정자를 또 누가
검증하느냐는 문제가 되므로 여기서 멈춘다.

- `if False: AGENT_CONTRACTS` 나 맨 이름 표현식은 `ast.Load` 이므로 근거로
  세어진다. 도달 가능성까지 보려면 제어 흐름 분석이 필요하다.
- 지목한 증명 Test 가 `assert True` 만 담아도 통과한다. 단언의 **내용** 이
  Capability 를 다루는지는 검사하지 않는다.
- 이름이 쓰였다는 것과 그 이름이 Capability 에 **참여한다** 는 것은 다르다.

따라서 이 검사는 **과대표기를 어렵게 만들 뿐 불가능하게 만들지 않는다.**
사람의 Review 를 대체하지 않는다.
"""
from __future__ import annotations

import ast
import subprocess
import sys

import pytest

# 조건 → 구현에 실제로 나타나야 할 이름. 문자열이 아니라 AST 상의 이름이다.
EVIDENCE = {
    # STEP 03 — LCEL 오케스트레이션. 선언한 것이 구현에서 실제로 쓰이는지 본다.
    "retrieval_and_answer_are_one_runnable": ["answer_chain"],
    "vector_backend_is_swappable": ["build_store", "store_backends"],
    "embedding_profile_is_reported": ["embedding_profile"],
    # STEP 04 — 하이브리드 검색과 자기 검증. 근거 이름은 s04 에 실재하는 심볼이다.
    "strategies_share_one_evaluation_set": ["QUESTIONS", "evaluate_strategy", "build_retriever"],
    "recall_and_rank_metrics_reported": ["recall_at_k", "reciprocal_rank", "hit_at_1"],
    "fusion_preserves_both_retrievers": ["hybrid_retriever", "keyword_retriever"],
    "answer_is_blocked_when_not_grounded": ["run_self_rag", "INSUFFICIENT"],
    # STEP 05 — 라이브러리가 도는 Agent. 근거 이름은 s05 에 실재하는 심볼이다.
    "tools_declared_from_function_signatures": ["tool", "LOCAL_TOOLS"],
    "the_agent_loop_comes_from_the_library": ["build_agent", "arun_agent"],
    "every_call_is_recorded_not_assumed": ["observations", "tools_called"],
    "the_step_budget_is_enforced": ["STEP_BUDGET", "step_budget"],
    "tools_arrive_from_a_separate_process": ["mcp_tools", "stdio_server"],
    "only_read_only_tools_are_exposed": ["READ_ONLY_TOOLS"],
    # STEP 06 — 순환·HITL·멀티에이전트. 근거 이름은 s06 에 실재하는 심볼이다.
    "the_graph_can_go_back": ["route_after_consolidate", "request_more"],
    "the_cycle_has_a_termination_rule": ["MAX_ROUNDS", "route_after_consolidate"],
    "execution_actually_stops": ["ask_human", "resume_with"],
    "the_paused_case_is_addressable": ["graph_config", "thread_store_durability"],
    "reviewers_run_in_parallel": ["AGENTS", "build_review_graph"],
    "the_merge_uses_the_latest_report": ["consolidate", "latest_report_per_agent"],
}


def _used_names(source: str) -> set[str]:
    """**읽히는** 이름만 모은다.

    주석과 docstring 은 AST 에 남지 않고 문자열 리터럴은 Name 노드가 아니므로
    자동으로 빠진다. 여기에 더해 **정의와 사용을 구분한다.** import 해 놓고 쓰지
    않거나, 대입만 하고 읽지 않거나, 빈 함수를 정의만 한 이름은 세지 않는다.
    그런 것은 근거가 아니라 장식이다.
    """
    used: set[str] = set()
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Load):
            used.add(node.id)          # 읽는 쪽만. 대입 대상(Store)은 제외
        elif isinstance(node, ast.Attribute) and isinstance(node.ctx, ast.Load):
            used.add(node.attr)
    return used


def _implementation_names(root, project_id: str) -> set[str]:
    """구현 코드에서 쓰인 이름. Test 는 제외한다."""
    names: set[str] = set()
    for path in (root / project_id).rglob("*.py"):
        if "tests" in path.parts:
            continue
        names |= _used_names(path.read_text(encoding="utf-8"))
    for path in (root / "shared").rglob("*.py"):
        names |= _used_names(path.read_text(encoding="utf-8"))
    return names


def _deferred(manifest) -> set[tuple[str, str, str]]:
    return {
        (d["project"], d["capability"], d["condition"])
        for d in manifest.get("deferred_conditions", [])
    }


def test_every_qualifying_condition_has_evidence_names(manifest):
    for name, body in manifest["capabilities"].items():
        for condition in body["qualifies_when"]:
            assert condition in EVIDENCE, f"{name}.{condition} 의 근거 이름이 없다"
            assert EVIDENCE[condition], condition


def test_declared_capabilities_reach_the_implementation(manifest, root):
    deferred = _deferred(manifest)
    for project in manifest["projects"]:
        names = _implementation_names(root, project["id"])
        for capability in project["capabilities"]:
            for condition in manifest["capabilities"][capability]["qualifies_when"]:
                if (project["id"], capability, condition) in deferred:
                    continue
                missing = [n for n in EVIDENCE[condition] if n not in names]
                assert missing == [], (
                    f"{project['id']} 가 '{capability}' 를 선언했지만 "
                    f"'{condition}' 의 근거 {missing} 가 구현에서 쓰이지 않는다"
                )


COSMETIC = '''
# OpenAIEmbeddings interrupt handoff
from somewhere import interrupt              # import 만 하고 쓰지 않는다
OpenAIEmbeddings = None                      # 대입만 하고 읽지 않는다
DOCS = "OpenAIEmbeddings interrupt handoff"


def handoff():                               # 정의만 하고 부르지 않는다
    """OpenAIEmbeddings interrupt handoff"""
    return 1
'''

REAL = '''
from langchain_openai import OpenAIEmbeddings
from langgraph.types import interrupt


def build():
    model = OpenAIEmbeddings(model="x")
    return interrupt({"model": model})
'''


def test_cosmetic_evidence_does_not_count():
    """주석·문자열·쓰이지 않는 import·대입·빈 정의는 근거가 아니다."""
    names = _used_names(COSMETIC)

    for disguise in ("OpenAIEmbeddings", "interrupt", "handoff"):
        assert disguise not in names, f"{disguise} 이 장식만으로 근거로 세어졌다"


def test_a_name_that_is_actually_used_does_count():
    """검사가 너무 엄격해 진짜 근거까지 떨어뜨리지 않는지 확인한다."""
    names = _used_names(REAL)

    assert "OpenAIEmbeddings" in names
    assert "interrupt" in names


def test_every_declared_capability_names_a_test_that_proves_it(manifest, root):
    """정적 검사는 이름이 쓰였다는 것만 말한다. 동작은 Test 가 증명한다."""
    for project in manifest["projects"]:
        proofs = project.get("capability_proofs", {})
        missing = [c for c in project["capabilities"] if c not in proofs]
        assert missing == [], (
            f"{project['id']} 의 capability {missing} 에 증명 Test 가 지목되지 않았다"
        )
        for capability, node_id in proofs.items():
            path = node_id.split("::")[0]
            assert (root / path).is_file(), (project["id"], capability, node_id)


def test_a_proof_test_belongs_to_the_project_it_proves(manifest):
    """다른 Project 의 Test 를 자기 증명으로 지목할 수 없다.

    지목 위치를 제한하지 않으면 아무 통과하는 Test 나 가리킬 수 있다.
    """
    for project in manifest["projects"]:
        declared = set(project["tests"])
        for capability, node_id in project.get("capability_proofs", {}).items():
            path = node_id.split("::")[0]
            assert path.startswith(f"{project['id']}/"), (
                f"{project['id']}/{capability} 가 남의 Test 를 가리킨다: {path}"
            )
            assert path in declared, (
                f"{path} 가 manifest 의 tests 목록에 없다"
            )


def test_the_named_proof_tests_actually_pass(manifest, root):
    """지목한 Test 를 실제로 돌린다.

    ``--collect-only`` 는 import 가능하다는 것만 말한다. 증명이라고 지목했으면
    통과해야 한다.
    """
    node_ids = [
        node_id
        for project in manifest["projects"]
        for node_id in project.get("capability_proofs", {}).values()
    ]
    assert node_ids, "증명 Test 가 하나도 지목되지 않았다"
    result = subprocess.run(
        [sys.executable, "-m", "pytest", "-q", "--no-header", "-p", "no:cacheprovider", *node_ids],
        cwd=root, capture_output=True, text=True,
    )
    assert result.returncode == 0, result.stdout[-2000:]


def test_a_proof_test_asserts_something(manifest, root):
    """단언이 없는 Test 는 무엇도 증명하지 않는다."""
    import ast as _ast

    for project in manifest["projects"]:
        for capability, node_id in project.get("capability_proofs", {}).items():
            path, _, name = node_id.partition("::")
            tree = _ast.parse((root / path).read_text(encoding="utf-8"))
            target = next(
                (n for n in tree.body
                 if isinstance(n, _ast.FunctionDef) and n.name == name), None
            )
            assert target is not None, f"{node_id} 가 존재하지 않는다"
            asserts = [n for n in _ast.walk(target) if isinstance(n, _ast.Assert)]
            assert asserts, f"{node_id} 에 단언이 없다"


def test_a_deferred_condition_that_is_already_met_must_be_removed(manifest, root):
    """유예가 구현보다 오래 살아남지 않게 한다."""
    for project_id, capability, condition in sorted(_deferred(manifest)):
        names = _implementation_names(root, project_id)
        satisfied = all(n in names for n in EVIDENCE[condition])
        assert not satisfied, (
            f"{project_id}/{capability}/{condition} 이 이미 충족되었다. "
            "curriculum_manifest.yaml 의 deferred_conditions 에서 지울 것"
        )


def test_deferred_conditions_are_reported_every_run(manifest, capsys):
    entries = manifest.get("deferred_conditions", [])
    for entry in entries:
        assert entry.get("phase"), entry
        assert entry.get("reason", "").strip(), entry
    lines = [
        f"  {e['project']} / {e['capability']} / {e['condition']}  → Phase {e['phase']}"
        for e in entries
    ]
    with capsys.disabled():
        print("\n[아직 충족하지 못한 자격 조건]\n" + ("\n".join(lines) if lines else "  없음"))
