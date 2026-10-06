"""The auditor against planted flaws: recall on seeded weaknesses, silence on a clean task."""

from __future__ import annotations

from pathlib import Path

import pytest

from audit_fixtures import FLAWS, clean_task, legacy_copy_all, native_few_cases, write_task
from sealgrade.audit.engine import audit_path, run_rules
from sealgrade.audit.model import Severity
from sealgrade.audit.rules import RULES, RULES_BY_ID
from sealgrade.audit.targets import find_tasks, is_task_dir, load_target


def findings_for(tmp_path: Path, files: dict[str, str]):  # type: ignore[no-untyped-def]
    root = write_task(tmp_path / "task", files)
    return run_rules(load_target(root))


def test_the_clean_task_has_no_findings_at_all(tmp_path: Path) -> None:
    findings = findings_for(tmp_path, clean_task())
    assert findings == [], [(f.rule_id, f.title) for f in findings]


@pytest.mark.parametrize("rule_id", sorted(FLAWS))
def test_each_planted_flaw_is_detected(rule_id: str, tmp_path: Path) -> None:
    findings = findings_for(tmp_path, FLAWS[rule_id](clean_task()))
    assert rule_id in {f.rule_id for f in findings}, (
        f"{rule_id} did not fire; got {[(f.rule_id, f.title) for f in findings]}"
    )


# Documented, intentional overlaps: some flaws legitimately trip a neighbouring rule too.
ALLOWED_SIDE_EFFECTS: dict[str, set[str]] = {
    "SG005": {"SG006"},  # the unpinned-config variant of the exit-code script
    "SG021": {"SG005", "SG006", "SG015"},  # an unanchored grep on program output is both
    "SG001": set(),
}


@pytest.mark.parametrize("rule_id", sorted(FLAWS))
def test_a_flaw_does_not_trigger_unrelated_rules(rule_id: str, tmp_path: Path) -> None:
    findings = findings_for(tmp_path, FLAWS[rule_id](clean_task()))
    extra = {f.rule_id for f in findings} - {rule_id} - ALLOWED_SIDE_EFFECTS.get(rule_id, set())
    assert not extra, f"{rule_id} also triggered {sorted(extra)}"


def test_legacy_layout_copying_the_whole_context_leaks_the_tests(tmp_path: Path) -> None:
    findings = findings_for(tmp_path, legacy_copy_all())
    sg001 = [f for f in findings if f.rule_id == "SG001"]
    assert sg001 and sg001[0].severity == Severity.HIGH
    assert "tests" in sg001[0].detail


def test_dockerignore_excluding_the_tests_silences_the_copy_all_finding(tmp_path: Path) -> None:
    files = {**legacy_copy_all(), ".dockerignore": "tests\nrun-tests.sh\ntask.yaml\n"}
    assert "SG001" not in {f.rule_id for f in findings_for(tmp_path, files)}


def test_native_tasks_with_few_cases_are_flagged(tmp_path: Path) -> None:
    findings = findings_for(tmp_path, native_few_cases())
    assert "SG026" in {f.rule_id for f in findings}


def test_separate_verifier_lowers_severity_of_config_discovery(tmp_path: Path) -> None:
    separate = FLAWS["SG006"](clean_task())
    shared = {
        **separate,
        "task.toml": separate["task.toml"].replace('environment_mode = "separate"\n', ""),
    }
    sev_separate = max(
        f.severity for f in findings_for(tmp_path / "a", separate) if f.rule_id == "SG006"
    )
    sev_shared = max(
        f.severity for f in findings_for(tmp_path / "b", shared) if f.rule_id == "SG006"
    )
    assert sev_separate < sev_shared


def test_harbors_own_documented_pattern_is_flagged_for_its_exit_code_reward(tmp_path: Path) -> None:
    """The reward pattern shown in Harbor's public docs trips the exit-code rule."""
    files = clean_task()
    files["tests/test.sh"] = """\
#!/bin/bash
uvx --python 3.12 --with pytest==8.4.1 pytest /tests/test_outputs.py
if [ $? -eq 0 ]; then
  echo 1 > /logs/verifier/reward.txt
else
  echo 0 > /logs/verifier/reward.txt
fi
"""
    del files["tests/check_report.py"]
    ids = {f.rule_id for f in findings_for(tmp_path, files)}
    assert {"SG005", "SG006"} <= ids


def test_every_rule_has_unique_id_metadata_and_known_classes() -> None:
    ids = [r.id for r in RULES]
    assert len(ids) == len(set(ids))
    assert RULES_BY_ID.keys() == set(ids)
    for rule in RULES:
        assert rule.classes and all(c in {f"V{i}" for i in range(1, 9)} for c in rule.classes)
        assert rule.title and rule.description and rule.remedy


def test_every_static_rule_has_a_planted_flaw_fixture() -> None:
    static = {r.id for r in RULES} - {"SG026", "SG027", "SG028"}
    assert static == set(FLAWS), static ^ set(FLAWS)


def test_recall_and_false_alarm_summary(tmp_path: Path) -> None:
    detected = sum(
        1
        for i, (rule_id, make) in enumerate(sorted(FLAWS.items()))
        if rule_id in {f.rule_id for f in findings_for(tmp_path / str(i), make(clean_task()))}
    )
    false_alarms = len(findings_for(tmp_path / "clean", clean_task()))
    assert detected == len(FLAWS)
    assert false_alarms == 0


# --- task discovery ---------------------------------------------------------------------------


def test_find_tasks_returns_the_task_itself_or_the_ones_below(tmp_path: Path) -> None:
    one = write_task(tmp_path / "one", clean_task())
    write_task(tmp_path / "set" / "a", clean_task())
    write_task(tmp_path / "set" / "b" / "nested", legacy_copy_all())
    assert find_tasks(one) == [one.resolve()]
    below = find_tasks(tmp_path / "set")
    assert {p.name for p in below} == {"a", "nested"}
    assert is_task_dir(one) and not is_task_dir(tmp_path / "set")


def test_audit_path_reports_per_task(tmp_path: Path) -> None:
    write_task(tmp_path / "good", clean_task())
    write_task(tmp_path / "bad", FLAWS["SG001"](clean_task()))
    reports = {r.target: r for r in audit_path(tmp_path)}
    assert set(reports) == {"good", "bad"}
    assert reports["good"].findings == []
    assert reports["bad"].max_severity() == Severity.HIGH


def test_the_repositorys_own_sample_tasks_are_native_and_mostly_clean(repo_root: Path) -> None:
    reports = audit_path(repo_root / "tasks")
    assert len(reports) >= 13
    assert all(r.kind == "sealgrade" for r in reports)
    assert all(r.count_at_least(Severity.MEDIUM) == 0 for r in reports)
