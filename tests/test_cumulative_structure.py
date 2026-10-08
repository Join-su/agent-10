"""누적 구조. 같은 것을 두 번 가르치지 않는지 검사하고, 개수는 강제하지 않는다."""


def _concepts(project) -> list:
    return project["new_concepts"]


def test_no_concept_is_introduced_in_two_projects(manifest):
    seen = {}
    for project in manifest["projects"]:
        for concept in _concepts(project):
            assert concept not in seen, (
                f"'{concept}' 가 {seen.get(concept)} 와 {project['id']} 양쪽에서 신규로 도입된다"
            )
            seen[concept] = project["id"]


def test_prerequisite_concepts_are_never_reintroduced(manifest):
    completed = set(manifest["course"]["prerequisite"]["completed_concepts"])
    for project in manifest["projects"]:
        repeated = completed & set(_concepts(project))
        assert repeated == set(), (project["id"], repeated)


def test_reused_concepts_come_from_somewhere_already_taught(manifest):
    taught = set(manifest["course"]["prerequisite"]["completed_concepts"])
    for project in manifest["projects"]:
        unknown = set(project["reused_not_reexplained"]) - taught
        assert unknown == set(), (
            f"{project['id']} 가 아직 가르치지 않은 개념을 재사용으로 표기했다: {unknown}"
        )
        taught |= set(_concepts(project))


def test_each_notebook_introduces_exactly_one_new_concept(manifest, contracts):
    limit = contracts["common"]["max_new_concepts_per_notebook"]
    for notebook in contracts["notebooks"]:
        count = len(notebook["new_concepts"])
        assert count == limit, (
            f"{notebook['file']} 의 신규 개념이 {count}개다. {limit}개를 넘으면 분할 대상이다"
        )


def test_notebook_concepts_exactly_cover_the_project_concepts(manifest, contracts):
    for project in manifest["projects"]:
        declared = set(_concepts(project))
        covered = {
            concept
            for notebook in contracts["notebooks"]
            if notebook["project"] == project["id"]
            for concept in notebook["new_concepts"]
        }
        assert covered == declared, (project["id"], declared ^ covered)


def test_each_project_has_exactly_one_integration_notebook(manifest):
    """통합 Notebook은 마지막 agent_technique다.

    engineering_practice는 그 뒤에 올 수 있다. 과정 전체에 걸친 방법론이라
    그 주차 기법의 통합 대상이 아니기 때문이다.
    """
    for project in manifest["projects"]:
        integrations = [n for n in project["notebooks"] if n.get("integration")]
        assert len(integrations) == 1, (project["id"], integrations)

        techniques = [n for n in project["notebooks"] if n["type"] == "agent_technique"]
        assert integrations[0] == techniques[-1], (
            f"{project['id']} 의 통합 Notebook이 마지막 agent_technique가 아니다"
        )
        assert all(
            n["type"] == "engineering_practice"
            for n in project["notebooks"][project["notebooks"].index(techniques[-1]) + 1:]
        ), f"{project['id']} 의 통합 Notebook 뒤에 agent_technique가 있다"


def test_notebook_counts_are_reported_not_asserted(manifest, capsys):
    """개수는 결과이지 목표가 아니다. 감소하지 않으면 경고만 남긴다."""
    counts = []
    for project in manifest["projects"]:
        technique = sum(
            1 for n in project["notebooks"] if n["type"] == "agent_technique"
        )
        practice = len(project["notebooks"]) - technique
        counts.append((project["id"], technique, practice))

    lines = [f"  {pid:24} agent_technique {t:2}  engineering_practice {p}"
             for pid, t, p in counts]
    technique_only = [t for _, t, _ in counts]
    if technique_only != sorted(technique_only, reverse=True):
        lines.append(
            "  경고: agent_technique 수가 감소하지 않는다. "
            "중복 도입이 없다면 문제가 아니지만 설계를 확인할 것"
        )
    with capsys.disabled():
        print("\n[누적 구조 리포트]\n" + "\n".join(lines))
