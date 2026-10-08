from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]


def _load(name: str) -> dict:
    return yaml.safe_load((ROOT / name).read_text(encoding="utf-8"))


@pytest.fixture(scope="session")
def manifest() -> dict:
    return _load("curriculum_manifest.yaml")


@pytest.fixture(scope="session")
def contracts() -> dict:
    return _load("notebook_contracts.yaml")


@pytest.fixture(scope="session")
def root() -> Path:
    return ROOT
