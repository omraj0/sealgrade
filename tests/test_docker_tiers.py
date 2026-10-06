"""Integration tests: every claim in an ``attack.toml`` is measured in real containers.

CI keeps pushes fast by narrowing the task sets through environment variables; the weekly workflow and
local runs use the defaults (three tasks for the attack matrix, every task for the controls).
"""

from __future__ import annotations

import os

import pytest

from sealgrade.matrix import run_controls, run_matrix
from sealgrade.spec import AttackSpec, TaskSpec

pytestmark = pytest.mark.docker

ALL_TIERS = ["t0", "t1", "t2", "t3"]


def _selection(variable: str, default: str) -> set[str]:
    return {s.strip() for s in os.environ.get(variable, default).split(",") if s.strip()}


MATRIX_TASKS = _selection("SEALGRADE_MATRIX_TASKS", "py-slugify,py-roman,py-merge-intervals")
CONTROL_TASKS = _selection("SEALGRADE_CONTROL_TASKS", "")  # empty = every task
JOBS = int(os.environ.get("SEALGRADE_JOBS", "2"))


@pytest.mark.parametrize("tier", ALL_TIERS)
def test_controls_hold_on_every_tier(tier: str, tasks: list[TaskSpec]) -> None:
    chosen = [t for t in tasks if not CONTROL_TASKS or t.id in CONTROL_TASKS]
    results = run_controls([tier], chosen, jobs=JOBS)
    failures = [r for r in results if not r.ok]
    assert not failures, failures


def test_documented_expectations_match_measurements(
    tasks: list[TaskSpec], attacks: list[AttackSpec]
) -> None:
    subset = [t for t in tasks if t.id in MATRIX_TASKS]
    result = run_matrix(ALL_TIERS, subset, attacks, with_controls=False, jobs=JOBS)
    assert result.mismatches() == []
