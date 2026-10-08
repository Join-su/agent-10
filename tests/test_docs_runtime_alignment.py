"""README·디렉터리·Test 경로가 manifest와 일치하는지. 구현 전에는 RED다."""
import pytest


def test_readme_records_the_naming_deviation(manifest, root):
    readme = root / "README.md"
    assert readme.is_file(), "README.md 가 없다"
    text = readme.read_text(encoding="utf-8")
    assert manifest["course"]["prerequisite"]["repository"] in text, "선행 과정 안내가 없다"
    for project in manifest["projects"]:
        assert project["id"] in text, f"{project['id']} 가 README에 없다"


def test_every_project_directory_exists(manifest, root):
    missing = [p["id"] for p in manifest["projects"] if not (root / p["id"]).is_dir()]
    assert missing == []


def test_every_declared_test_file_exists(manifest, root):
    missing = [t for p in manifest["projects"] for t in p["tests"]
               if not (root / t).is_file()]
    assert missing == [], f"선언되었으나 없는 Test {len(missing)}개: {missing[:3]} ..."


def test_every_declared_course_test_exists(manifest, root):
    missing = [t for t in manifest["course_tests"] if not (root / t).is_file()]
    assert missing == [], missing


def test_every_test_file_on_disk_is_declared(manifest, root):
    """선언되지 않은 Test 파일이 생기면 정본이 현실을 못 따라간 것이다."""
    declared = set(manifest["course_tests"])
    declared |= {t for p in manifest["projects"] for t in p["tests"]}
    on_disk = {
        str(path.relative_to(root))
        for path in root.glob("tests/test_*.py")
    } | {
        str(path.relative_to(root))
        for p in manifest["projects"]
        for path in (root / p["id"]).glob("tests/test_*.py")
    }
    assert on_disk - declared == set(), sorted(on_disk - declared)


def test_every_declared_deliverable_exists(manifest, root):
    missing = [d for p in manifest["projects"] for d in p["deliverables"]
               if not (root / d).exists()]
    assert missing == []


def test_instruction_docs_do_not_use_posix_only_command_syntax(root):
    """따라 하라고 적은 명령은 세 운영체제에서 동작해야 한다.

    `APP_MODE=live uv run ...` 는 macOS·Linux 에서만 된다. Windows cmd 는
    `'APP_MODE'은(는) 내부 또는 외부 명령... 이 아닙니다` 를 낸다. 실제로 다른
    환경에서 받은 사람이 여기서 막혔다.

    설정은 `.env` 에 적고 `--env-file .env` 로 읽게 한다. 그러면 명령이 같다.

    코드 블록만 본다. 산문에서 "이렇게 하면 안 된다"고 예를 드는 것은 막지 않는다.
    """
    import re

    instruction_docs = [
        root / "README.md",
        root / "docs" / "running-the-app.md",
    ]
    # VAR=값 뒤에 명령이 오는 형태. export 나 .env 줄은 해당하지 않는다.
    posix_prefix = re.compile(r"^[A-Z][A-Z0-9_]*=\S+\s+\S+", re.M)

    offenders = []
    scanned = 0
    for path in instruction_docs:
        if not path.is_file():
            continue
        for block in re.findall(r"```bash\n(.*?)```", path.read_text(encoding="utf-8"), re.S):
            scanned += 1
            for line in block.splitlines():
                stripped = line.strip()
                if stripped.startswith("#") or not stripped:
                    continue
                if posix_prefix.match(stripped):
                    offenders.append(f"{path.name}: {stripped}")

    assert scanned >= 8, f"코드 블록을 {scanned}개만 봤다. 이 검사가 거의 아무것도 보지 않는다."
    assert not offenders, (
        "Windows 에서 동작하지 않는 명령이 있다. .env 에 적고 --env-file 로 읽게 한다:\n  "
        + "\n  ".join(offenders)
    )


def test_the_prerequisite_courses_exist_in_the_manifest(manifest):
    """선행 과정이 정본에 남아 있어야 한다. 과제 10 은 STEP 03~06(v2) 다음 단계다.

    하나만 적혀 있으면 다음 사람이 Python 기초까지 다시 가르치려 한다.
    """
    courses = manifest["course"]["prerequisite"]["courses"]
    ids = [c["id"] for c in courses]
    assert ids == ["hanwha_0902", "agent-workflow-lab", "agent-workflow-lab-v2"], f"선행 과정이 {ids} 다"
    for course in courses:
        assert course["covers"], f"{course['id']} 가 무엇을 다뤘는지 비어 있다"


def test_every_endpoint_in_the_run_guide_exists(root):
    """실행 가이드가 적은 endpoint 가 실제로 있어야 한다.

    표에 `/threads/{id}` 라고 적혀 있었는데 실제 경로는 `/threads/{thread_id}` 였다.
    문서를 그대로 따라 한 사람이 틀린 주소를 치게 된다. 표는 사람이 손으로
    고치는 곳이라 조용히 어긋난다.
    """
    import importlib
    import re

    guide = (root / "docs" / "running-the-app.md").read_text(encoding="utf-8")
    rows = re.findall(r"^\| (STEP 0\d|과제 10) \| `(\w+) (/[\w/{}-]+)` \|", guide, re.M)
    assert len(rows) >= 5, f"표에서 endpoint 를 {len(rows)}개만 찾았다. 표 모양이 바뀌었다"

    apps = {"과제 10": "task10_maintenance"}
    missing = []
    for step, method, path in rows:
        app = importlib.import_module(f"{apps[step]}.app").app
        if not any(r.path == path and method in getattr(r, "methods", set())
                   for r in app.routes):
            missing.append(f"{step} {method} {path}")
    assert missing == [], missing


def test_every_uvicorn_command_in_the_docs_names_a_real_module(root):
    """문서가 띄우라는 모듈이 실재해야 한다. 지워진 앱을 띄우라고 한 적이 있다."""
    import importlib
    import re

    text = "\n".join(p.read_text(encoding="utf-8")
                     for p in [*(root / "docs").glob("*.md"), root / "README.md"])
    modules = set(re.findall(r"uvicorn ([a-z0-9_]+)\.app:app", text))
    assert modules == {"task10_maintenance"}, f"문서가 이 저장소에 없는 앱을 띄우라고 한다: {modules}"
    for module in sorted(modules):
        importlib.import_module(f"{module}.app")
