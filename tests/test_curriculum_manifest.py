"""정본 자체가 모순되지 않는지. 구현이 없어도 통과해야 한다."""
import pytest

REQUIRED_PROJECT_FIELDS = {
    "id", "week", "difficulty", "title", "domain", "user_problem", "user_outputs",
    "capabilities", "endpoints", "new_concepts", "reused_not_reexplained",
    "notebooks", "tests", "deliverables", "safety_invariants", "completion",
}


def test_top_level_sections_exist(manifest):
    for key in ("version", "course", "python", "audience", "safety_invariants",
                "capabilities", "projects"):
        assert key in manifest, key


def test_audience_declares_both_sides(manifest):
    audience = manifest["audience"]
    assert audience["assumed"], "안다고 가정할 것이 비어 있다"
    assert audience["not_assumed"], "모른다고 가정할 것이 비어 있다"
    assert not set(audience["assumed"]) & set(audience["not_assumed"])


def test_every_project_declares_the_required_fields(manifest):
    for project in manifest["projects"]:
        missing = REQUIRED_PROJECT_FIELDS - set(project)
        assert missing == set(), (project.get("id"), missing)


def test_project_ids_weeks_and_difficulties_are_unique(manifest):
    projects = manifest["projects"]
    for field in ("id", "week", "difficulty"):
        values = [p[field] for p in projects]
        assert len(set(values)) == len(values), (field, values)


def test_difficulty_matches_week_order(manifest):
    for project in manifest["projects"]:
        assert project["difficulty"] == project["week"], project["id"]


def test_endpoint_paths_are_unique_within_a_project(manifest):
    for project in manifest["projects"]:
        paths = [f"{e['method']} {e['path']}" for e in project["endpoints"]]
        assert len(set(paths)) == len(paths), (project["id"], paths)


def test_declared_capabilities_are_defined_with_qualifying_conditions(manifest):
    defined = manifest["capabilities"]
    for name, body in defined.items():
        assert body.get("qualifies_when"), f"{name}에 자격 조건이 없다"
    for project in manifest["projects"]:
        unknown = set(project["capabilities"]) - set(defined)
        assert unknown == set(), (project["id"], unknown)
