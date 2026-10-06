"""Steps shared by every tier: image caching, seeding the sandbox, running the agent's script."""

from __future__ import annotations

from typing import Any

from docker.errors import ImageNotFound

from sealgrade.runner import naive_assets
from sealgrade.runner.docker_backend import build_image, client, exec_bash, put_files
from sealgrade.runner.models import Submission
from sealgrade.spec.task import TaskSpec

AGENT_SCRIPT_PATH = "/tmp/agent.sh"


def ensure_naive_image(task: TaskSpec) -> str:
    """Build (once per content hash) the weak-harness image for ``task`` and return its tag."""
    context = naive_assets.build_context(task)
    tag = f"sealgrade/naive-{task.id}:{naive_assets.context_digest(context)[:12]}"
    cli = client()
    try:
        cli.images.get(tag)
    except ImageNotFound:
        build_image(cli, tag, context)
    return tag


def agent_env(task: TaskSpec, submission: Submission) -> dict[str, str]:
    """What an agent legitimately knows from the prompt: the module, function and artifact names."""
    env = {
        "SG_MODULE": task.judge.module,
        "SG_FUNCTION": task.judge.function,
        "SG_ARTIFACT": task.agent.artifacts[0],
    }
    env.update(submission.env)
    return env


def seed_workdir(container: Any, task: TaskSpec, submission: Submission) -> None:
    """Place the submission's files in the agent's working directory."""
    put_files(container, task.agent.workdir, submission.files)


def run_agent_script(container: Any, task: TaskSpec, submission: Submission) -> tuple[int, str]:
    """Run the submission's script the way a shell-capable agent would, as its final action."""
    if submission.script is None:
        return 0, ""
    put_files(container, "/tmp", {"agent.sh": submission.script}, executable=["agent.sh"])
    return exec_bash(
        container,
        f"bash {AGENT_SCRIPT_PATH}",
        timeout=task.agent.timeout_sec,
        workdir=task.agent.workdir,
        env=agent_env(task, submission),
    )


def parse_reward(text: str | None) -> float:
    """Parse ``reward.txt``. Anything that is not a finite number in [0, 1] counts as 0."""
    if text is None:
        return 0.0
    try:
        value = float(text.strip().splitlines()[0])
    except (ValueError, IndexError):
        return 0.0
    if value != value or value < 0.0 or value > 1.0:  # NaN or out of range
        return 0.0
    return value
