"""Tier T3, "strict": three containers, data crosses boundaries only through a firewall.

1. **Agent phase** (container A): the submission's shell and files live here. The image holds no
   tests and no ground truth. Non-root, no capabilities, read-only root filesystem, no network.
2. **Artifact firewall** (host): only the declared artifact files are copied out, each as
   exactly one regular file of bounded size. Symlinks, links, devices, odd names and oversize
   data are refused.
3. **Candidate execution** (container B, fresh): receives the validated artifacts and the *inputs*
   only, runs the candidate and returns **outputs as bytes**. It never sees an expected value, and
   it is destroyed when it finishes, so nothing outlives it.
4. **Judge** (container C, fresh): holds the ground truth and compares data. It never
   executes candidate code. The controller validates its report, computes the reward itself and
   signs a record.

The tier fails closed: any refusal or malformed data is a reward of 0. A weaker container than the
policy demands is not a grade, it is an error.
"""

from __future__ import annotations

import json
import time
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from sealgrade.runner import verdict as signing
from sealgrade.runner.common import agent_env
from sealgrade.runner.docker_backend import client, unique_name
from sealgrade.runner.firewall import (
    RESULT_LIMITS,
    VERDICT_LIMITS,
    FirewallError,
    fetch_file,
)
from sealgrade.runner.models import Submission, Verdict
from sealgrade.runner.phases import RunContext, Upload, run_phase
from sealgrade.runner.policy import ContainerPolicy
from sealgrade.runner.strict_assets import ensure_runtime_image
from sealgrade.spec.task import TaskSpec

EXEC_TIMEOUT_SEC = 60
JUDGE_TIMEOUT_SEC = 30
CASE_TIMEOUT_SEC = 5
AGENT_UID = 10001


class _Failure(BaseModel):
    model_config = ConfigDict(extra="forbid")
    i: int = Field(ge=0)
    why: str = Field(max_length=100)


class JudgeReport(BaseModel):
    """The judge's report. Anything that does not fit this schema is rejected."""

    model_config = ConfigDict(extra="forbid", strict=True)
    schema_version: int = Field(alias="schema")
    total: int = Field(ge=0)
    passed: int = Field(ge=0)
    failures: list[_Failure] = Field(max_length=50)
    error: str | None = Field(max_length=300)


class T3Strict:
    tier = "t3"

    def __init__(self, policy: ContainerPolicy | None = None) -> None:
        self.policy = policy or ContainerPolicy()
        self._key = signing.load_key()

    # ------------------------------------------------------------------------------------

    def grade(self, task: TaskSpec, submission: Submission) -> Verdict:
        started = time.monotonic()
        cli = client()
        image = ensure_runtime_image(cli)
        ctx = RunContext(cli, unique_name("t3"))
        timings: dict[str, float] = {}
        try:
            reward, detail, record = self._grade(ctx, image, task, submission, timings)
        finally:
            ctx.cleanup()
        return Verdict(self.tier, reward, detail, time.monotonic() - started, record)

    def _refuse(self, reason: str) -> tuple[float, str, dict[str, Any] | None]:
        return 0.0, f"refused: {reason}", None

    def _grade(
        self,
        ctx: RunContext,
        image: str,
        task: TaskSpec,
        submission: Submission,
        timings: dict[str, float],
    ) -> tuple[float, str, dict[str, Any] | None]:
        policy = self.policy
        workdir = task.agent.workdir

        # 1. AGENT PHASE -------------------------------------------------------------------
        agent_files: dict[str, Upload] = {
            name: Upload(data, mode=0o644, uid=AGENT_UID) for name, data in submission.files.items()
        }
        agent_files["INSTRUCTION.md"] = Upload(
            task.instruction_text().encode(), mode=0o644, uid=AGENT_UID
        )
        if submission.script is not None:
            agent_files["agent.sh"] = Upload(submission.script, mode=0o755, uid=AGENT_UID)
            command = [
                "timeout",
                "-k",
                "2",
                str(task.agent.timeout_sec),
                "bash",
                f"{workdir}/agent.sh",
            ]
        else:
            command = ["true"]
        agent = run_phase(
            ctx,
            name="agent",
            image=image,
            command=command,
            policy=policy,
            mounts={workdir: "work"},
            uploads={workdir: agent_files},
            env=agent_env(task, submission),
            timeout_sec=task.agent.timeout_sec + 10,
        )
        timings["agent"] = round(agent.elapsed_sec, 3)

        # 2. ARTIFACT FIREWALL -------------------------------------------------------------
        artifacts: dict[str, bytes] = {}
        for name in task.agent.artifacts:
            try:
                data = fetch_file(agent.container, f"{workdir}/{name}")
            except FirewallError as exc:
                return self._refuse(f"artifact {name!r}: {exc}")
            if data is None:
                return self._refuse(f"artifact {name!r} was not produced")
            try:
                data.decode("utf-8")
            except UnicodeDecodeError:
                return self._refuse(f"artifact {name!r} is not valid UTF-8")
            artifacts[name] = data

        # 3. CANDIDATE EXECUTION ------------------------------------------------------------
        cases = task.cases()
        inputs = "".join(
            json.dumps({"i": i, "args": c.args, "kwargs": c.kwargs}) + "\n"
            for i, c in enumerate(cases)
        )
        meta = json.dumps(
            {
                "module": task.judge.module,
                "function": task.judge.function,
                "case_timeout": CASE_TIMEOUT_SEC,
            }
        )
        exec_uploads: dict[str, Upload] = {
            f"candidate/{n}": Upload(d) for n, d in artifacts.items()
        }
        exec_uploads["inputs.jsonl"] = Upload(inputs.encode())
        exec_uploads["meta.json"] = Upload(meta.encode())
        execution = run_phase(
            ctx,
            name="exec",
            image=image,
            command=["python", "-I", "/opt/sg/sg_exec.py"],
            policy=policy,
            mounts={"/inbox": "exec-in", "/outbox": "exec-out"},
            uploads={"/inbox": exec_uploads},
            timeout_sec=EXEC_TIMEOUT_SEC,
        )
        timings["exec"] = round(execution.elapsed_sec, 3)
        try:
            results = fetch_file(execution.container, "/outbox/results.jsonl", RESULT_LIMITS)
        except FirewallError as exc:
            return self._refuse(f"results file: {exc}")

        # 4. JUDGE --------------------------------------------------------------------------
        cases_bytes = task.cases_path().read_bytes()
        truth = "".join(
            json.dumps({"expected": c.expected, "raises": c.raises}) + "\n" for c in cases
        )
        judge_uploads: dict[str, Upload] = {"cases.jsonl": Upload(truth.encode())}
        if results is not None:
            judge_uploads["results.jsonl"] = Upload(results)
        judge = run_phase(
            ctx,
            name="judge",
            image=image,
            command=["python", "-I", "/opt/sg/sg_judge.py"],
            policy=policy,
            mounts={"/inbox": "judge-in", "/outbox": "judge-out"},
            uploads={"/inbox": judge_uploads},
            timeout_sec=JUDGE_TIMEOUT_SEC,
        )
        timings["judge"] = round(judge.elapsed_sec, 3)
        try:
            raw_report = fetch_file(judge.container, "/outbox/verdict.json", VERDICT_LIMITS)
            if raw_report is None:
                return self._refuse("judge produced no verdict")
            report = JudgeReport.model_validate_json(raw_report)
        except (FirewallError, ValidationError, ValueError) as exc:
            return self._refuse(f"judge report invalid: {type(exc).__name__}")
        if report.schema_version != 1:
            return self._refuse("unknown judge report version")

        # 5. THE CONTROLLER DECIDES ----------------------------------------------------------
        all_passed = (
            report.error is None and report.total == len(cases) and report.passed == report.total
        )
        reward = 1.0 if all_passed else 0.0
        record: dict[str, Any] = {
            "task": task.id,
            "tier": self.tier,
            "run": ctx.run_id,
            "reward": reward,
            "cases_sha256": signing.sha256_hex(cases_bytes),
            "artifacts_sha256": {n: signing.sha256_hex(d) for n, d in sorted(artifacts.items())},
            "results_sha256": signing.sha256_hex(results or b""),
            "judge": {"total": report.total, "passed": report.passed, "error": report.error},
            "image": image,
            "timings_sec": timings,
        }
        signature = signing.sign(record, self._key)
        why = report.error or ", ".join(f"#{f.i}:{f.why}" for f in report.failures[:3])
        detail = f"passed {report.passed}/{report.total}" + (f" ({why})" if why else "")
        return reward, detail, {**record, "signature": signature}

    def verify(self, record: dict[str, Any]) -> bool:
        """Check a record produced by this instance (same key)."""
        body = {k: v for k, v in record.items() if k != "signature"}
        return signing.verify(body, str(record.get("signature", "")), self._key)
