"""Running the rules over targets and collecting a report."""

from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path

from sealgrade.audit.model import AuditReport, AuditTarget, Finding, Rule, Severity
from sealgrade.audit.rules import RULES
from sealgrade.audit.targets import find_tasks, load_target


def run_rules(target: AuditTarget, rules: Iterable[Rule] = RULES) -> list[Finding]:
    """All findings for ``target``, de-duplicated and ordered most severe first."""
    seen: set[tuple[str, str, int, str]] = set()
    findings: list[Finding] = []
    for rule in rules:
        for finding in rule.check(target):
            key = (finding.rule_id, finding.path, finding.line, finding.detail)
            if key not in seen:
                seen.add(key)
                findings.append(finding)
    findings.sort(key=lambda f: (-int(f.severity), f.rule_id, f.path, f.line))
    return findings


def audit_path(path: Path, rules: Iterable[Rule] = RULES) -> list[AuditReport]:
    """Audit ``path`` (one task, or a directory of tasks) with the static rules."""
    reports: list[AuditReport] = []
    for task_dir in find_tasks(path):
        target = load_target(task_dir)
        reports.append(
            AuditReport(target=target.task_id, kind=target.kind, findings=run_rules(target, rules))
        )
    return reports


def worst(reports: Iterable[AuditReport]) -> Severity | None:
    """The highest severity across ``reports``."""
    return max((s for r in reports if (s := r.max_severity()) is not None), default=None)
