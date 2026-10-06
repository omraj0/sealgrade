"""Tier T1, "typical": a separate verifier container, but still weakly isolated.

Better than T0 in one way: the agent container is stopped and discarded before verification,
so processes and in-place edits to the image filesystem do not survive. Weak in the ways that
matter here: both containers use the *same image* (tests inside it), run as root, and share the
work and log volumes. The verdict is read from a report the submission may have influenced.
"""

from __future__ import annotations

import contextlib
import time
from typing import Any

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


class T1Typical:
    tier = "t1"

    def grade(self, task: TaskSpec, submission: Submission) -> Verdict:
        started = time.monotonic()
        image = ensure_naive_image(task)
        cli = client()
        run_id = unique_name("t1")
        work = cli.volumes.create(name=f"{run_id}-work", labels={LABEL: "1"})
        logs = cli.volumes.create(name=f"{run_id}-logs", labels={LABEL: "1"})
        mounts = {
            work.name: {"bind": task.agent.workdir, "mode": "rw"},
            logs.name: {"bind": "/logs", "mode": "rw"},
        }
        containers: list[Any] = []
        try:
            agent = cli.containers.create(
                image,
                command=["sleep", "900"],
                working_dir=task.agent.workdir,
                volumes=mounts,
                labels={LABEL: "1"},
                name=f"{run_id}-agent",
            )
            containers.append(agent)
            agent.start()
            seed_workdir(agent, task, submission)
            agent_code, _ = run_agent_script(agent, task, submission)
            agent.remove(force=True)  # processes and image-layer edits die with the container

            verifier = cli.containers.create(
                image,
                command=["sleep", "900"],
                working_dir=task.agent.workdir,
                volumes=mounts,
                labels={LABEL: "1"},
                name=f"{run_id}-verifier",
            )
            containers.append(verifier)
            verifier.start()
            verify_code, _ = exec_bash(
                verifier, "bash /tests/run_t1.sh", timeout=VERIFY_TIMEOUT_SEC
            )
            reward = parse_reward(read_text(verifier, "/logs/verifier/reward.txt"))
            tail = read_text(verifier, "/logs/verifier/pytest.out", tail_bytes=1200) or ""
        finally:
            for resource in (*containers, work, logs):
                with contextlib.suppress(Exception):  # may already be gone
                    resource.remove(force=True)
        detail = f"agent_exit={agent_code} verifier_exit={verify_code}\n{tail}".strip()
        return Verdict(self.tier, reward, detail, time.monotonic() - started)
