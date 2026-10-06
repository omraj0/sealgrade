"""Stages shared by the hardened tiers (T2 and T3): the agent phase and the artifact firewall."""

from __future__ import annotations

from sealgrade.runner.common import agent_env
from sealgrade.runner.firewall import FirewallError, fetch_file
from sealgrade.runner.models import Submission
from sealgrade.runner.phases import RunContext, Upload, run_phase
from sealgrade.runner.policy import ContainerPolicy
from sealgrade.spec.task import TaskSpec

AGENT_UID = 10001


def run_agent_stage(
    ctx: RunContext,
    image: str,
    task: TaskSpec,
    submission: Submission,
    policy: ContainerPolicy,
    timings: dict[str, float],
) -> dict[str, bytes] | str:
    """Run the submission in an isolated agent container; pull artifacts through the firewall.

    Returns the validated artifact bytes by name, or a human-readable refusal reason (a ``str``).
    """
    workdir = task.agent.workdir
    files: dict[str, Upload] = {
        name: Upload(data, mode=0o644, uid=AGENT_UID) for name, data in submission.files.items()
    }
    files["INSTRUCTION.md"] = Upload(task.instruction_text().encode(), mode=0o644, uid=AGENT_UID)
    if submission.script is not None:
        files["agent.sh"] = Upload(submission.script, mode=0o755, uid=AGENT_UID)
        command = ["timeout", "-k", "2", str(task.agent.timeout_sec), "bash", f"{workdir}/agent.sh"]
    else:
        command = ["true"]
    agent = run_phase(
        ctx,
        name="agent",
        image=image,
        command=command,
        policy=policy,
        mounts={workdir: "work"},
        uploads={workdir: files},
        env=agent_env(task, submission),
        timeout_sec=task.agent.timeout_sec + 10,
    )
    timings["agent"] = round(agent.elapsed_sec, 3)

    artifacts: dict[str, bytes] = {}
    for name in task.agent.artifacts:
        try:
            data = fetch_file(agent.container, f"{workdir}/{name}")
        except FirewallError as exc:
            return f"artifact {name!r}: {exc}"
        if data is None:
            return f"artifact {name!r} was not produced"
        try:
            data.decode("utf-8")
        except UnicodeDecodeError:
            return f"artifact {name!r} is not valid UTF-8"
        artifacts[name] = data
    return artifacts
