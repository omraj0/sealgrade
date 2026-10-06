"""Task correctness without Docker: the oracle must pass and bad work must fail."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

from sealgrade.runner import naive_assets
from sealgrade.spec import TaskSpec


def _run_generated_tests(task: TaskSpec, files: dict[str, bytes], tmp_path: Path) -> int:
    work = tmp_path / "work"
    verify = work / "_verify"
    verify.mkdir(parents=True)
    for name, data in files.items():
        (work / name).write_bytes(data)
    (verify / "test_task.py").write_text(naive_assets.render_test_file(task), encoding="utf-8")
    (verify / "cases.jsonl").write_bytes(task.cases_path().read_bytes())
    proc = subprocess.run(
        [sys.executable, "-m", "pytest", "_verify/test_task.py", "-q", "-p", "no:cacheprovider"],
        cwd=work,
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )
    return proc.returncode


def test_oracle_passes_every_case(tasks: list[TaskSpec], tmp_path: Path) -> None:
    for task in tasks:
        assert _run_generated_tests(task, task.oracle_files(), tmp_path / task.id) == 0, task.id


def test_near_miss_is_rejected(tasks: list[TaskSpec], tmp_path: Path) -> None:
    for task in tasks:
        assert _run_generated_tests(task, task.near_miss_files(), tmp_path / task.id) != 0, task.id


def test_empty_submission_is_rejected(tasks: list[TaskSpec], tmp_path: Path) -> None:
    for task in tasks:
        assert _run_generated_tests(task, {}, tmp_path / task.id) != 0, task.id


def test_committed_cases_are_up_to_date(repo_root: Path) -> None:
    proc = subprocess.run(
        [sys.executable, str(repo_root / "tools" / "gen_cases.py"), "--check"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0, proc.stderr


@pytest.mark.parametrize("script", ["RUN_T0", "RUN_T1", "CHECK_JUNIT"])
def test_harness_scripts_have_unix_line_endings(script: str) -> None:
    assert "\r" not in getattr(naive_assets, script)
