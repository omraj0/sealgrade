"""Run attacks and controls against harness tiers and compare the outcome with what we claimed.

Outcome vocabulary for one attack on one tier, across every task and repeat:

* ``exploit``: every run was graded as a pass although the payload does not solve the task
* ``blocked``: no run was graded as a pass
* ``partial``: some did and some did not (a flaky defence is not a defence)
"""

from __future__ import annotations

import json
from collections.abc import Callable, Iterable
from dataclasses import asdict, dataclass, field
from typing import Literal

from sealgrade.runner import Harness, Submission, get_harness
from sealgrade.spec.attack import AttackSpec
from sealgrade.spec.task import TaskSpec

Observed = Literal["exploit", "blocked", "partial"]


@dataclass(frozen=True)
class Cell:
    """One attack, one task, one tier, ``runs`` repeats."""

    task: str
    attack: str
    tier: str
    successes: int
    runs: int
    elapsed_sec: float


@dataclass(frozen=True)
class ControlResult:
    """A sanity check that a tier still grades honest work correctly."""

    task: str
    tier: str
    control: Literal["oracle", "noop", "near_miss"]
    reward: float
    expected_reward: float

    @property
    def ok(self) -> bool:
        return self.reward == self.expected_reward


@dataclass
class MatrixResult:
    tiers: list[str]
    attacks: list[AttackSpec]
    cells: list[Cell] = field(default_factory=list)
    controls: list[ControlResult] = field(default_factory=list)

    # --- aggregation ------------------------------------------------------------------

    def observed(self, attack_id: str, tier: str) -> Observed | None:
        relevant = [c for c in self.cells if c.attack == attack_id and c.tier == tier]
        if not relevant:
            return None
        successes = sum(c.successes for c in relevant)
        runs = sum(c.runs for c in relevant)
        if successes == 0:
            return "blocked"
        return "exploit" if successes == runs else "partial"

    def mismatches(self) -> list[tuple[str, str, str | None, str | None]]:
        """``(attack, tier, expected, observed)`` where the claim and the measurement disagree."""
        bad: list[tuple[str, str, str | None, str | None]] = []
        for attack in self.attacks:
            for tier in self.tiers:
                expected = attack.expected.for_tier(tier)
                observed = self.observed(attack.id, tier)
                if expected is not None and expected != observed:
                    bad.append((attack.id, tier, expected, observed))
        return bad

    def exploit_counts(self) -> dict[str, tuple[int, int]]:
        """Per tier: attacks that fully succeeded, and attacks measured."""
        counts: dict[str, tuple[int, int]] = {}
        for tier in self.tiers:
            seen = [self.observed(a.id, tier) for a in self.attacks]
            measured = [s for s in seen if s is not None]
            counts[tier] = (sum(1 for s in measured if s == "exploit"), len(measured))
        return counts

    def control_failures(self) -> list[ControlResult]:
        return [c for c in self.controls if not c.ok]

    @property
    def ok(self) -> bool:
        return not self.mismatches() and not self.control_failures()

    # --- serialisation ----------------------------------------------------------------

    def to_json(self) -> str:
        payload = {
            "tiers": self.tiers,
            "attacks": [
                {
                    "id": a.id,
                    "title": a.title,
                    "classes": a.classes,
                    "expected": a.expected.model_dump(),
                    "observed": {t: self.observed(a.id, t) for t in self.tiers},
                }
                for a in self.attacks
            ],
            "cells": [asdict(c) for c in self.cells],
            "controls": [{**asdict(c), "ok": c.ok} for c in self.controls],
            "exploit_counts": {
                t: {"exploited": e, "measured": m} for t, (e, m) in self.exploit_counts().items()
            },
            "ok": self.ok,
        }
        return json.dumps(payload, indent=2, sort_keys=True)


ProgressFn = Callable[[str], None]


def grade_many(
    harness: Harness, task: TaskSpec, submission: Submission, runs: int
) -> tuple[int, float]:
    """How many of ``runs`` repeats the harness graded as a pass, and the mean seconds per run."""
    verdicts = [harness.grade(task, submission) for _ in range(runs)]
    mean = sum(v.elapsed_sec for v in verdicts) / len(verdicts)
    return sum(1 for v in verdicts if v.passed), mean


def attack_submission(attack: AttackSpec) -> Submission:
    return Submission(name=attack.id, files=attack.payload_files(), script=attack.script_bytes())


def run_controls(
    tiers: Iterable[str], tasks: Iterable[TaskSpec], progress: ProgressFn | None = None
) -> list[ControlResult]:
    """Oracle must pass, a do-nothing submission and a near-miss must fail, on every tier."""
    results: list[ControlResult] = []
    for tier in tiers:
        harness = get_harness(tier)
        for task in tasks:
            plan: list[tuple[Literal["oracle", "noop", "near_miss"], Submission, float]] = [
                ("oracle", Submission("oracle", files=task.oracle_files()), 1.0),
                ("noop", Submission("noop"), 0.0),
                ("near_miss", Submission("near-miss", files=task.near_miss_files()), 0.0),
            ]
            for name, submission, expected in plan:
                if progress:
                    progress(f"control {name} / {task.id} / {tier}")
                verdict = harness.grade(task, submission)
                results.append(ControlResult(task.id, tier, name, verdict.reward, expected))
    return results


def run_matrix(
    tiers: list[str],
    tasks: list[TaskSpec],
    attacks: list[AttackSpec],
    *,
    with_controls: bool = True,
    progress: ProgressFn | None = None,
) -> MatrixResult:
    result = MatrixResult(tiers=tiers, attacks=attacks)
    for tier in tiers:
        harness = get_harness(tier)
        for attack in attacks:
            submission = attack_submission(attack)
            for task in tasks:
                if progress:
                    progress(f"{attack.id} / {task.id} / {tier}")
                successes, mean_sec = grade_many(harness, task, submission, attack.repeat)
                result.cells.append(
                    Cell(task.id, attack.id, tier, successes, attack.repeat, round(mean_sec, 3))
                )
    if with_controls:
        result.controls = run_controls(tiers, tasks, progress)
    return result
