"""파일시스템이 Inventory와 일치하는지. Notebook 작성 전에는 RED다."""
import pytest


def test_every_declared_notebook_exists(manifest, root):
    missing = [
        f"{p['id']}/notebooks/{n['file']}"
        for p in manifest["projects"]
        for n in p["notebooks"]
        if not (root / p["id"] / "notebooks" / n["file"]).is_file()
    ]
    assert missing == [], f"선언되었으나 없는 Notebook {len(missing)}개: {missing[:3]} ..."


def test_no_undeclared_notebook_exists(manifest, root):
    declared = {
        root / p["id"] / "notebooks" / n["file"]
        for p in manifest["projects"]
        for n in p["notebooks"]
    }
    found = set(root.glob("*/notebooks/*.ipynb"))
    assert found - declared == set()
