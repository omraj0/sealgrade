"""SARIF 2.1.0 output, so findings show up in GitHub code scanning."""

from __future__ import annotations

import json
from collections.abc import Iterable
from typing import Any

from sealgrade import __version__
from sealgrade.audit.model import AuditReport, Severity
from sealgrade.audit.rules import RULES

_LEVEL = {
    Severity.HIGH: "error",
    Severity.MEDIUM: "warning",
    Severity.LOW: "note",
    Severity.INFO: "note",
}
SCHEMA = "https://json.schemastore.org/sarif-2.1.0.json"


def to_sarif(reports: Iterable[AuditReport]) -> dict[str, Any]:
    """A SARIF log with one run covering every report."""
    rules = [
        {
            "id": rule.id,
            "name": rule.id,
            "shortDescription": {"text": rule.title},
            "fullDescription": {"text": rule.description},
            "help": {"text": rule.remedy},
            "defaultConfiguration": {"level": _LEVEL[rule.severity]},
            "properties": {"tags": ["security", "evaluation", *rule.classes]},
        }
        for rule in RULES
    ]
    results: list[dict[str, Any]] = []
    for report in reports:
        for finding in report.findings:
            location: dict[str, Any] = {
                "physicalLocation": {
                    "artifactLocation": {"uri": f"{report.target}/{finding.path}".strip("/")}
                }
            }
            if finding.line:
                location["physicalLocation"]["region"] = {"startLine": finding.line}
            results.append(
                {
                    "ruleId": finding.rule_id,
                    "level": _LEVEL[finding.severity],
                    "message": {"text": f"{finding.title}. {finding.detail}"},
                    "locations": [location],
                }
            )
    return {
        "$schema": SCHEMA,
        "version": "2.1.0",
        "runs": [
            {
                "tool": {
                    "driver": {
                        "name": "sealgrade",
                        "version": __version__,
                        "informationUri": "https://github.com/omraj0/sealgrade",
                        "rules": rules,
                    }
                },
                "results": results,
            }
        ],
    }


def sarif_text(reports: Iterable[AuditReport]) -> str:
    return json.dumps(to_sarif(reports), indent=2)
