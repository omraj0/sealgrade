"""Integration tests: every claim in a ``attack.toml`` is measured in real containers."""

from __future__ import annotations

import pytest

from sealgrade.matrix import run_controls, run_matrix
from sealgrade.spec import AttackSpec, TaskSpec

pytestmark = pytest.mark.docker

NAIVE_TIERS = ["t0", "t1"]


@pytest.mark.parametrize("tier", NAIVE_TIERS)
def test_controls_hold_on_every_tier(tier: str, tasks: list[TaskSpec]) -> None:
    results = run_controls([tier], tasks)
    failures = [r for r in results if not r.ok]
    assert not failures, failures


def test_documented_expectations_match_measurements(
    tasks: list[TaskSpec], attacks: list[AttackSpec]
) -> None:
    result = run_matrix(NAIVE_TIERS, tasks, attacks, with_controls=False)
    assert result.mismatches() == []
