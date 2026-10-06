"""Auditor building blocks: Dockerfile parsing, local grading, mutation, SARIF and the CLI."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from audit_fixtures import FLAWS, clean_task, write_task
from sealgrade.audit.dockerfile import (
    base_images,
    copy_sources,
    dockerignore_patterns,
    final_user,
    ignored,
    image_pin,
    parse_dockerfile,
)
from sealgrade.audit.engine import audit_path
from sealgrade.audit.local import grade_locally
from sealgrade.audit.mutation import run_mutation
from sealgrade.audit.sarif import to_sarif
from sealgrade.cli import app
from sealgrade.spec import TaskSpec, load_task

runner = CliRunner()


# --- Dockerfile parsing -------------------------------------------------------------------------


def test_parser_joins_continuations_and_skips_comments() -> None:
    text = (
        "# comment\nFROM python:3.12\nRUN apt-get update \\\n"
        "    && apt-get install -y curl\n\nUSER agent\n"
    )
    instructions = parse_dockerfile(text)
    assert [i.op for i in instructions] == ["FROM", "RUN", "USER"]
    assert "apt-get install -y curl" in instructions[1].args
    assert instructions[1].line == 3  # the instruction's first physical line


def test_copy_sources_handles_flags_and_json_form() -> None:
    one = parse_dockerfile("COPY --chown=1:1 a.txt dir/ /dest/")[0]
    two = parse_dockerfile('COPY ["x y.txt", "z.txt", "/dest/"]')[0]
    assert copy_sources(one) == ["a.txt", "dir/"]
    assert copy_sources(two) == ["x y.txt", "z.txt"]


def test_final_user_is_the_last_user_instruction() -> None:
    assert final_user(parse_dockerfile("USER a\nUSER b:grp\n")) == "b"
    assert final_user(parse_dockerfile("FROM x\n")) is None


@pytest.mark.parametrize(
    ("ref", "pin"),
    [
        ("python", "latest"),
        ("python:latest", "latest"),
        ("python:3.12", "tag"),
        ("ghcr.io/org/img:1.2", "tag"),
        ("python:3.12@sha256:" + "0" * 64, "digest"),
        ("localhost:5000/img", "latest"),
    ],
)
def test_image_pin(ref: str, pin: str) -> None:
    assert image_pin(ref) == pin


def test_base_images_ignore_stage_flags_and_aliases() -> None:
    instructions = parse_dockerfile(
        "FROM --platform=linux/amd64 python:3.12 AS build\nFROM build\n"
    )
    assert base_images(instructions) == ["python:3.12", "build"]


def test_dockerignore_matching_with_exceptions() -> None:
    patterns = dockerignore_patterns("# c\ntests\n*.log\n!keep.log\n")
    assert ignored("tests/test_a.py", patterns)
    assert ignored("a/b/debug.log", patterns)
    assert not ignored("keep.log", patterns)
    assert not ignored("src/main.py", patterns)


# --- local grading and mutation -----------------------------------------------------------------


def _task(tasks: list[TaskSpec], task_id: str) -> TaskSpec:
    return next(t for t in tasks if t.id == task_id)


def test_local_grading_accepts_the_oracle_and_rejects_the_near_miss(tasks: list[TaskSpec]) -> None:
    task = _task(tasks, "py-gcd-lcm")
    oracle = task.oracle_files()["solution.py"].decode()
    near_miss = task.near_miss_files()["solution.py"].decode()
    assert grade_locally(task, oracle).all_passed
    assert not grade_locally(task, near_miss).all_passed
    assert not grade_locally(task, "def broken(:\n").all_passed


def test_mutation_report_adds_up_and_is_deterministic(tasks: list[TaskSpec]) -> None:
    task = _task(tasks, "py-gcd-lcm")
    first = run_mutation(task, max_mutants=20, seed=3, jobs=4)
    second = run_mutation(task, max_mutants=20, seed=3, jobs=4)
    assert first.total == first.killed + first.survived + first.invalid
    assert first.killed > 0
    assert 0.0 <= first.score <= 1.0
    assert first.as_dict() == second.as_dict()


def test_a_task_with_thin_cases_has_survivors_and_a_low_score(tmp_path: Path) -> None:
    root = tmp_path / "thin"
    (root / "oracle").mkdir(parents=True)
    (root / "near_miss").mkdir()
    (root / "task.toml").write_text(
        '[task]\nid = "thin"\ntitle = "t"\n\n[agent]\nartifacts = ["solution.py"]\n\n'
        '[judge]\nfunction = "classify"\n',
        encoding="utf-8",
    )
    (root / "instruction.md").write_text("x\n", encoding="utf-8")
    (root / "cases.jsonl").write_text('{"args": [5], "expected": "big"}\n', encoding="utf-8")
    source = (
        "def classify(n):\n"
        "    if n > 100:\n        return 'huge'\n"
        "    if n > 10:\n        return 'medium'\n"
        "    if n > 1:\n        return 'big'\n"
        "    return 'small'\n"
    )
    (root / "oracle" / "solution.py").write_text(source, encoding="utf-8")
    (root / "near_miss" / "solution.py").write_text(
        "def classify(n):\n    return 'x'\n", encoding="utf-8"
    )
    report = run_mutation(load_task(root), max_mutants=40, jobs=4)
    assert report.survived >= 3
    assert report.score < 0.9
    assert any(s.diff for s in report.survivors)


# --- SARIF --------------------------------------------------------------------------------------


def test_sarif_has_the_required_structure(tmp_path: Path) -> None:
    write_task(tmp_path / "bad", FLAWS["SG001"](clean_task()))
    sarif = to_sarif(audit_path(tmp_path))
    assert sarif["version"] == "2.1.0" and "$schema" in sarif
    run = sarif["runs"][0]
    assert run["tool"]["driver"]["name"] == "sealgrade"
    rule_ids = {r["id"] for r in run["tool"]["driver"]["rules"]}
    assert {"SG001", "SG027", "SG028"} <= rule_ids
    result = next(r for r in run["results"] if r["ruleId"] == "SG001")
    assert result["level"] == "error"
    location = result["locations"][0]["physicalLocation"]
    assert location["artifactLocation"]["uri"].endswith("environment/Dockerfile")
    assert location["region"]["startLine"] >= 1
    json.dumps(sarif)  # serialisable


# --- CLI ----------------------------------------------------------------------------------------


def test_cli_exit_codes_follow_the_severity_threshold(tmp_path: Path) -> None:
    good = write_task(tmp_path / "good", clean_task())
    bad = write_task(tmp_path / "bad", FLAWS["SG001"](clean_task()))
    assert runner.invoke(app, ["audit", str(good)]).exit_code == 0
    assert runner.invoke(app, ["audit", str(bad)]).exit_code == 1
    assert runner.invoke(app, ["audit", str(bad), "--fail-on", "none"]).exit_code == 0
    assert runner.invoke(app, ["audit", str(tmp_path / "nothing-here")]).exit_code != 0


def test_cli_json_and_sarif_and_html_outputs(tmp_path: Path) -> None:
    bad = write_task(tmp_path / "bad", FLAWS["SG004"](clean_task()))
    as_json = runner.invoke(app, ["audit", str(bad), "--format", "json", "--fail-on", "none"])
    data = json.loads(as_json.stdout)
    assert data["summary"]["findings_by_severity"]["high"] >= 1
    assert data["tasks"][0]["findings"][0]["rule"] == "SG004"

    sarif_path = tmp_path / "out" / "r.sarif"
    result = runner.invoke(
        app, ["audit", str(bad), "--format", "sarif", "--out", str(sarif_path), "--fail-on", "none"]
    )
    assert result.exit_code == 0 and json.loads(sarif_path.read_text())["version"] == "2.1.0"

    html_path = tmp_path / "out" / "r.html"
    runner.invoke(
        app, ["audit", str(bad), "--format", "html", "--out", str(html_path), "--fail-on", "none"]
    )
    html = html_path.read_text()
    assert "SG004" in html and "<script" not in html


def test_cli_mutation_option_on_a_sample_task(repo_root: Path) -> None:
    result = runner.invoke(
        app,
        [
            "audit",
            str(repo_root / "tasks" / "py-gcd-lcm"),
            "--mutation",
            "--mutants",
            "15",
            "--format",
            "json",
        ],
    )
    assert result.exit_code == 0, result.output
    mutation = json.loads(result.stdout)["tasks"][0]["mutation"]
    assert mutation["mutants"] > 0 and 0.0 <= mutation["score"] <= 1.0
