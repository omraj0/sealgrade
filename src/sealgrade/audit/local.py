"""Grading a candidate on this machine, without Docker, using the strict tier's guest scripts.

This is **only** for code derived from a trusted source (the oracle solution and its mutants),
where speed matters and hostility does not: mutation testing runs hundreds of variants. Anything
untrusted must go through a real tier.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from importlib import resources
from pathlib import Path

from sealgrade.spec.task import TaskSpec


@dataclass(frozen=True)
class LocalResult:
    passed: int
    total: int
    error: str | None = None

    @property
    def all_passed(self) -> bool:
        return self.error is None and self.total > 0 and self.passed == self.total


def _guest(name: str) -> str:
    return str(resources.files("sealgrade.runner.guest").joinpath(name))


def grade_locally(task: TaskSpec, source: str, *, timeout_sec: int = 30) -> LocalResult:
    """Run ``source`` as the task's solution and compare with the ground truth."""
    cases = task.cases()
    with tempfile.TemporaryDirectory(prefix="sg-audit-") as tmp:
        root = Path(tmp)
        exec_in, exec_out = root / "exec-in", root / "exec-out"
        judge_in, judge_out = root / "judge-in", root / "judge-out"
        (exec_in / "candidate").mkdir(parents=True)
        for directory in (exec_out, judge_in, judge_out):
            directory.mkdir()
        (exec_in / "candidate" / f"{task.judge.module}.py").write_text(source, encoding="utf-8")
        (exec_in / "inputs.jsonl").write_text(
            "".join(
                json.dumps({"i": i, "args": c.args, "kwargs": c.kwargs}) + "\n"
                for i, c in enumerate(cases)
            ),
            encoding="utf-8",
        )
        (exec_in / "meta.json").write_text(
            json.dumps(
                {"module": task.judge.module, "function": task.judge.function, "case_timeout": 5}
            ),
            encoding="utf-8",
        )
        env = {**os.environ, "SG_INBOX": str(exec_in), "SG_OUTBOX": str(exec_out)}
        try:
            subprocess.run(
                [sys.executable, "-I", _guest("sg_exec.py")],
                env=env,
                timeout=timeout_sec,
                check=False,
                capture_output=True,
            )
        except subprocess.TimeoutExpired:
            return LocalResult(0, len(cases), "timed out")

        (judge_in / "cases.jsonl").write_text(
            "".join(json.dumps({"expected": c.expected, "raises": c.raises}) + "\n" for c in cases),
            encoding="utf-8",
        )
        results = exec_out / "results.jsonl"
        if results.exists():
            (judge_in / "results.jsonl").write_bytes(results.read_bytes())
        env = {**os.environ, "SG_INBOX": str(judge_in), "SG_OUTBOX": str(judge_out)}
        subprocess.run(
            [sys.executable, "-I", _guest("sg_judge.py")],
            env=env,
            timeout=timeout_sec,
            check=False,
            capture_output=True,
        )
        verdict = judge_out / "verdict.json"
        if not verdict.exists():
            return LocalResult(0, len(cases), "no verdict")
        report = json.loads(verdict.read_text(encoding="utf-8"))
        return LocalResult(int(report["passed"]), int(report["total"]), report.get("error"))
