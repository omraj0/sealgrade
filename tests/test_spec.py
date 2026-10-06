from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from sealgrade.spec import AttackSpec, TaskSpec
from sealgrade.spec.task import AgentSection, JudgeSection


def test_tasks_are_found_and_named_after_their_folder(tasks: list[TaskSpec]) -> None:
    assert len(tasks) >= 3
    for task in tasks:
        assert task.root.name == task.id


def test_every_task_has_cases_oracle_and_near_miss(tasks: list[TaskSpec]) -> None:
    for task in tasks:
        assert task.cases(), task.id
        assert set(task.oracle_files()) == set(task.agent.artifacts)
        assert set(task.near_miss_files()) == set(task.agent.artifacts)
        assert task.instruction_text().strip()


def test_attacks_are_named_after_their_folder_and_payloads_exist(attacks: list[AttackSpec]) -> None:
    assert len(attacks) >= 8
    seen: set[str] = set()
    for attack in attacks:
        assert attack.root.name == attack.id
        assert attack.id not in seen
        seen.add(attack.id)
        assert attack.payload_files() is not None  # raises if a payload file is missing
        if attack.agent_script:
            assert attack.script_bytes()
        assert attack.files or attack.agent_script, f"{attack.id} does nothing"


def test_every_attack_documents_its_naive_tier_expectation(attacks: list[AttackSpec]) -> None:
    for attack in attacks:
        assert attack.expected.t0 == "exploit", (
            f"{attack.id}: T0 is the baseline every attack must beat"
        )
        assert attack.expected.t1 in ("exploit", "blocked")


def test_shell_payloads_use_unix_line_endings(attacks: list[AttackSpec]) -> None:
    for attack in attacks:
        script = attack.script_bytes()
        if script is not None:
            assert b"\r\n" not in script, f"{attack.id}/agent.sh has CRLF line endings"


@pytest.mark.parametrize(
    "bad", ["../escape.py", "/etc/passwd", "a/../../b.py", "dir\\file.py", "", "ok\0.py"]
)
def test_artifact_paths_must_stay_inside_the_workdir(bad: str) -> None:
    with pytest.raises(ValidationError):
        AgentSection(artifacts=[bad])


@pytest.mark.parametrize("bad", ["1abc", "has space", "a-b", "x;y"])
def test_judge_identifiers_are_validated(bad: str) -> None:
    with pytest.raises(ValidationError):
        JudgeSection(function=bad)


def test_attack_classes_must_be_in_the_taxonomy(tmp_path: Path) -> None:
    with pytest.raises(ValidationError):
        AttackSpec(id="x", title="t", summary="s", classes=["V9"], root=tmp_path)


def test_attack_payload_destinations_cannot_escape_the_workdir(tmp_path: Path) -> None:
    with pytest.raises(ValidationError):
        AttackSpec(
            id="x", title="t", summary="s", classes=["V1"], files={"../evil.py": "p"}, root=tmp_path
        )
