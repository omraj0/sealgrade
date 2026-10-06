"""Strict-tier behaviour that only shows up with real containers."""

from __future__ import annotations

import hashlib
from typing import Any

import pytest

from sealgrade.runner import get_harness
from sealgrade.runner.docker_backend import LABEL, client
from sealgrade.runner.models import Submission
from sealgrade.runner.tier_t3 import T3Strict
from sealgrade.spec import TaskSpec

pytestmark = pytest.mark.docker


def _task(tasks: list[TaskSpec], task_id: str = "py-slugify") -> TaskSpec:
    return next(t for t in tasks if t.id == task_id)


def _grade(tasks: list[TaskSpec], submission: Submission, task_id: str = "py-slugify") -> Any:
    return get_harness("t3").grade(_task(tasks, task_id), submission)


def test_the_oracle_passes_and_produces_a_verifiable_signed_record(tasks: list[TaskSpec]) -> None:
    harness = get_harness("t3")
    assert isinstance(harness, T3Strict)
    task = _task(tasks)
    verdict = harness.grade(task, Submission("oracle", files=task.oracle_files()))
    assert verdict.passed and verdict.record is not None
    assert harness.verify(verdict.record)
    assert verdict.record["judge"] == {
        "total": len(task.cases()),
        "passed": len(task.cases()),
        "error": None,
    }
    assert set(verdict.record["timings_sec"]) == {"agent", "exec", "judge"}


def test_a_signed_record_cannot_be_edited(tasks: list[TaskSpec]) -> None:
    harness = get_harness("t3")
    assert isinstance(harness, T3Strict)
    task = _task(tasks)
    verdict = harness.grade(task, Submission("near-miss", files=task.near_miss_files()))
    assert verdict.record is not None and verdict.record["reward"] == 0.0
    forged = {**verdict.record, "reward": 1.0}
    assert not harness.verify(forged)


def test_no_containers_or_volumes_survive_a_run(tasks: list[TaskSpec]) -> None:
    cli = client()
    before = (
        len(cli.containers.list(all=True, filters={"label": LABEL})),
        len(cli.volumes.list(filters={"label": LABEL})),
    )
    _grade(tasks, Submission("noop"))
    after = (
        len(cli.containers.list(all=True, filters={"label": LABEL})),
        len(cli.volumes.list(filters={"label": LABEL})),
    )
    assert after == before


def test_missing_artifact_is_refused_not_graded(tasks: list[TaskSpec]) -> None:
    verdict = _grade(tasks, Submission("noop"))
    assert verdict.reward == 0.0 and "was not produced" in verdict.detail


def test_symlink_artifact_is_refused(tasks: list[TaskSpec]) -> None:
    script = b"#!/bin/bash\nln -s /etc/passwd /work/solution.py\n"
    verdict = _grade(tasks, Submission("symlink", script=script))
    assert verdict.reward == 0.0 and "not a regular file" in verdict.detail


def test_directory_artifact_is_refused(tasks: list[TaskSpec]) -> None:
    script = b"#!/bin/bash\nmkdir /work/solution.py\necho x > /work/solution.py/inner.py\n"
    verdict = _grade(tasks, Submission("dir", script=script))
    assert verdict.reward == 0.0 and verdict.detail.startswith("refused")


def test_oversize_artifact_is_refused(tasks: list[TaskSpec]) -> None:
    script = b"#!/bin/bash\nhead -c 3000000 /dev/zero | tr '\\0' 'a' > /work/solution.py\n"
    verdict = _grade(tasks, Submission("big", script=script))
    assert verdict.reward == 0.0 and "limit" in verdict.detail


def test_non_utf8_artifact_is_refused(tasks: list[TaskSpec]) -> None:
    script = b"#!/bin/bash\nprintf '\\xff\\xfe\\x00' > /work/solution.py\n"
    verdict = _grade(tasks, Submission("binary", script=script))
    assert verdict.reward == 0.0 and "UTF-8" in verdict.detail


def test_the_agent_container_has_no_network_and_cannot_write_outside_its_workdir(
    tasks: list[TaskSpec],
) -> None:
    """The script reports what it could do by embedding the answers in a (wrong) solution file."""
    script = b"""#!/bin/bash
net=blocked
python3 - <<'PY' && net=OPEN
import socket
socket.create_connection(("1.1.1.1", 53), timeout=3)
PY
root=blocked
touch /etc/probe 2>/dev/null && root=WRITABLE
tests=absent
[ -e /tests ] && tests=PRESENT
echo "def slugify(t): return '$net-$root-$tests'" > /work/solution.py
"""
    task = _task(tasks)
    verdict = _grade(tasks, Submission("probe", script=script))
    assert verdict.reward == 0.0
    # Read the solution back out of a fresh run's artifact hash: re-run and inspect via the record.
    assert verdict.record is not None

    expected = hashlib.sha256(b"def slugify(t): return 'blocked-blocked-absent'\n").hexdigest()
    assert verdict.record["artifacts_sha256"]["solution.py"] == expected, (
        "the agent container is weaker than the policy says"
    )
    assert task.agent.artifacts == ["solution.py"]
