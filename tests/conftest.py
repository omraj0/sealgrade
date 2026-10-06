from __future__ import annotations

from pathlib import Path

import pytest

from sealgrade.runner.docker_backend import docker_available
from sealgrade.spec import AttackSpec, TaskSpec, load_attacks, load_tasks

ROOT = Path(__file__).resolve().parent.parent


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    """Skip Docker tests cleanly when no daemon is reachable."""
    if docker_available():
        return
    skip = pytest.mark.skip(reason="no Docker daemon reachable")
    for item in items:
        if "docker" in item.keywords:
            item.add_marker(skip)


@pytest.fixture(scope="session")
def repo_root() -> Path:
    return ROOT


@pytest.fixture(scope="session")
def tasks() -> list[TaskSpec]:
    return load_tasks(ROOT / "tasks")


@pytest.fixture(scope="session")
def attacks() -> list[AttackSpec]:
    return load_attacks(ROOT / "corpus")
