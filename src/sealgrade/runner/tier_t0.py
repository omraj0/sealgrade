"""Tier T0, "naive": one container does everything.

The agent works in a container that also holds the tests. When it is done, the *same* container
(same filesystem, same processes, same PATH) runs the tests and writes the reward file.
This is how many quick evaluation scripts are written, and it is the baseline we measure against.
"""

from __future__ import annotations

import time

from sealgrade.runner.common import (
    ensure_naive_image,
    parse_reward,
    run_agent_script,
    seed_workdir,
)
from sealgrade.runner.docker_backend import LABEL, client, exec_bash, read_text, unique_name
from sealgrade.runner.models import Submission, Verdict
from sealgrade.spec.task import TaskSpec

VERIFY_TIMEOUT_SEC = 120


class T0Naive:
    tier = "t0"

    def grade(self, task: TaskSpec, submission: Submission) -> Verdict:
        started = time.monotonic()
        image = ensure_naive_image(task)
        cli = client()
        container = cli.containers.create(
            image,
            command=["sleep", "900"],
            working_dir=task.agent.workdir,
            labels={LABEL: "1"},
            name=unique_name("t0"),
        )
        try:
            container.start()
            seed_workdir(container, task, submission)
            agent_code, _ = run_agent_script(container, task, submission)
            verify_code, _ = exec_bash(
                container, "bash /tests/run_t0.sh", timeout=VERIFY_TIMEOUT_SEC
            )
            reward = parse_reward(read_text(container, "/logs/reward.txt"))
            tail = read_text(container, "/logs/pytest.out", tail_bytes=1200) or ""
        finally:
            container.remove(force=True)
        detail = f"agent_exit={agent_code} verifier_exit={verify_code}\n{tail}".strip()
        return Verdict(self.tier, reward, detail, time.monotonic() - started)
