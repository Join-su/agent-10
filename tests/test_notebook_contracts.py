"""Notebook 계약이 manifest Inventory와 어긋나지 않는지. 구현이 없어도 통과해야 한다."""
REQUIRED_FIELDS = {
    "file", "project", "order", "notebook_type", "new_concepts", "objective",
    "primitives", "fixtures", "observe", "assertions", "app_link",
}


def test_common_block_fixes_the_shared_rules(contracts):
    common = contracts["common"]
    for key in ("required_headings", "min_markdown_cells", "min_code_cells",
                "fixture_prefixes", "require_assertion",
                "require_success_and_failure_fixture",
                "max_new_concepts_per_notebook", "forbidden_imports", "forbidden_calls"):
        assert key in common, key
    assert common["max_new_concepts_per_notebook"] == 1


def test_contracts_cover_exactly_the_manifest_inventory(manifest, contracts):
    declared = {
        (p["id"], n["file"]) for p in manifest["projects"] for n in p["notebooks"]
    }
    contracted = {(n["project"], n["file"]) for n in contracts["notebooks"]}
    assert contracted == declared


def test_every_contract_has_the_required_fields(contracts):
    for notebook in contracts["notebooks"]:
        missing = REQUIRED_FIELDS - set(notebook)
        assert missing == set(), (notebook.get("file"), missing)


def test_every_contract_runs_a_success_and_a_failure_fixture(contracts):
    for notebook in contracts["notebooks"]:
        fixtures = notebook["fixtures"]
        assert fixtures.get("success"), notebook["file"]
        assert fixtures.get("failure"), notebook["file"]


def test_primitives_and_assertions_are_not_empty(contracts):
    for notebook in contracts["notebooks"]:
        assert notebook["primitives"], notebook["file"]
        assert notebook["assertions"], notebook["file"]


def test_fixture_names_use_the_agreed_prefixes(contracts):
    prefixes = tuple(contracts["common"]["fixture_prefixes"]) + (
        "evaluation_cases", "failure_cases",
    )
    for notebook in contracts["notebooks"]:
        for primitive in notebook["primitives"]:
            assert primitive.startswith(prefixes), (notebook["file"], primitive)


def test_notebook_type_and_order_agree_with_the_manifest(manifest, contracts):
    by_key = {(n["project"], n["file"]): n for n in contracts["notebooks"]}
    for project in manifest["projects"]:
        for order, declared in enumerate(project["notebooks"], start=1):
            contract = by_key[(project["id"], declared["file"])]
            assert contract["notebook_type"] == declared["type"], declared["file"]
            assert contract["order"] == order, declared["file"]
            assert bool(contract.get("integration")) == bool(declared.get("integration"))
