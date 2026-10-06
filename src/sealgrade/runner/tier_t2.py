"""Tier T2, "compat": hardened pytest-in-a-container for tests that must import the candidate.

Compared with T1 it adds everything that does not require giving up the pytest model: the
agent phase and artifact firewall of the strict tier, a verification container that is non-root,
read-only, offline and discarded, isolated interpreter mode (``python -I``), a pinned pytest
configuration, plugin autoload off, and a reward that requires the report to account for exactly the
expected number of tests with no failure, error or skip.

What it cannot do: the candidate is imported into the same process as the tests, and the
ground truth is in the same container. In-process attacks (reading the answer file, inspecting
the caller's frame, patching pytest, forging the report at exit) therefore still work. That is
documented and measured; use the strict tier (T3) when the task allows it.
"""

from __future__ import annotations

import time
from typing import Any

from sealgrade.runner import verdict as signing
from sealgrade.runner.compat_assets import PYTEST_COMMAND, ensure_compat_image, test_files
from sealgrade.runner.docker_backend import client, unique_name
from sealgrade.runner.firewall import VERDICT_LIMITS, FirewallError, fetch_file
from sealgrade.runner.junit import JunitError, parse_junit
from sealgrade.runner.models import Submission, Verdict
from sealgrade.runner.phases import RunContext, Upload, run_phase
from sealgrade.runner.policy import ContainerPolicy
from sealgrade.runner.stages import run_agent_stage
from sealgrade.spec.task import TaskSpec

VERIFY_TIMEOUT_SEC = 120


class T2Compat:
    tier = "t2"

    def __init__(self, policy: ContainerPolicy | None = None) -> None:
        self.policy = policy or ContainerPolicy()
        self._key = signing.load_key()

    def grade(self, task: TaskSpec, submission: Submission) -> Verdict:
        started = time.monotonic()
        cli = client()
        image = ensure_compat_image(cli)
        ctx = RunContext(cli, unique_name("t2"))
        timings: dict[str, float] = {}
        try:
            reward, detail, record = self._grade(ctx, image, task, submission, timings)
        finally:
            ctx.cleanup()
        return Verdict(self.tier, reward, detail, time.monotonic() - started, record)

    def _grade(
        self,
        ctx: RunContext,
        image: str,
        task: TaskSpec,
        submission: Submission,
        timings: dict[str, float],
    ) -> tuple[float, str, dict[str, Any] | None]:
        staged = run_agent_stage(ctx, image, task, submission, self.policy, timings)
        if isinstance(staged, str):
            return 0.0, f"refused: {staged}", None
        artifacts = staged

        uploads: dict[str, Upload] = {f"candidate/{n}": Upload(d) for n, d in artifacts.items()}
        uploads.update({name: Upload(data) for name, data in test_files(task).items()})
        verify = run_phase(
            ctx,
            name="verify",
            image=image,
            command=PYTEST_COMMAND,
            policy=self.policy,
            mounts={"/inbox": "verify-in", "/outbox": "verify-out"},
            uploads={"/inbox": uploads},
            env={"PYTEST_DISABLE_PLUGIN_AUTOLOAD": "1"},
            timeout_sec=VERIFY_TIMEOUT_SEC,
        )
        timings["verify"] = round(verify.elapsed_sec, 3)

        expected = len(task.cases())
        try:
            report = fetch_file(verify.container, "/outbox/junit.xml", VERDICT_LIMITS)
        except FirewallError as exc:
            return 0.0, f"refused: report: {exc}", None
        if report is None:
            return 0.0, "no test report was produced", None
        try:
            totals = parse_junit(report)
        except JunitError as exc:
            return 0.0, f"refused: report: {exc}", None

        passed = totals.tests == expected and totals.clean
        reward = 1.0 if passed else 0.0
        record: dict[str, Any] = {
            "task": task.id,
            "tier": self.tier,
            "run": ctx.run_id,
            "reward": reward,
            "cases_sha256": signing.sha256_hex(task.cases_path().read_bytes()),
            "artifacts_sha256": {n: signing.sha256_hex(d) for n, d in sorted(artifacts.items())},
            "report_sha256": signing.sha256_hex(report),
            "totals": {
                "tests": totals.tests,
                "failures": totals.failures,
                "errors": totals.errors,
                "skipped": totals.skipped,
                "expected": expected,
            },
            "image": image,
            "timings_sec": timings,
        }
        signature = signing.sign(record, self._key)
        detail = (
            f"tests {totals.tests}/{expected}, failures {totals.failures}, "
            f"errors {totals.errors}, skipped {totals.skipped}"
        )
        return reward, detail, {**record, "signature": signature}
