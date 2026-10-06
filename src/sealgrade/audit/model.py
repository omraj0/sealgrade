"""Data model for the auditor: findings, rules and the normalised view of a task."""

from __future__ import annotations

import re
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from enum import IntEnum
from pathlib import Path
from typing import Any, Literal


def is_tests_path(path: str) -> bool:
    """Whether ``path`` is verifier material in either the flat or the multi-step layout."""
    return path.startswith("tests/") or bool(re.match(r"^steps/[^/]+/tests/", path))


class Severity(IntEnum):
    """Ordered so that ``severity >= Severity.MEDIUM`` reads naturally."""

    INFO = 0
    LOW = 1
    MEDIUM = 2
    HIGH = 3

    @property
    def label(self) -> str:
        return self.name.lower()

    @classmethod
    def parse(cls, value: str) -> Severity:
        try:
            return cls[value.upper()]
        except KeyError:
            raise ValueError(f"unknown severity {value!r}") from None


@dataclass(frozen=True)
class Finding:
    """One issue found in a task."""

    rule_id: str
    severity: Severity
    title: str
    detail: str
    path: str = ""
    line: int = 0
    classes: tuple[str, ...] = ()

    def as_dict(self) -> dict[str, Any]:
        return {
            "rule": self.rule_id,
            "severity": self.severity.label,
            "title": self.title,
            "detail": self.detail,
            "path": self.path,
            "line": self.line,
            "classes": list(self.classes),
        }


@dataclass(frozen=True)
class DockerInstruction:
    """One logical Dockerfile instruction (continuations joined)."""

    line: int
    op: str
    args: str


@dataclass
class AuditTarget:
    """A task, normalised so that rules do not care which format it came from."""

    root: Path
    kind: Literal["sealgrade", "harbor"]
    task_id: str
    files: dict[str, str]  # relative POSIX path -> text (text files only, size-limited)
    config: dict[str, Any] = field(default_factory=dict)
    dockerfile_path: str | None = None
    dockerfile: list[DockerInstruction] = field(default_factory=list)
    dockerignore: list[str] = field(default_factory=list)
    build_context: str = ""  # directory (relative) the image is built from

    # --- conveniences used by rules ----------------------------------------------------

    def paths(self, prefix: str = "", suffix: str = "") -> list[str]:
        return sorted(p for p in self.files if p.startswith(prefix) and p.endswith(suffix))

    def text(self, path: str) -> str:
        return self.files.get(path, "")

    @property
    def tests_files(self) -> list[str]:
        """Files under ``tests/`` (or ``steps/<name>/tests/`` for multi-step Harbor tasks)."""
        return [p for p in self.files if is_tests_path(p)]

    @property
    def verifier_scripts(self) -> list[str]:
        return [p for p in self.tests_files if p.endswith((".sh", ".bat", ".cmd", ".ps1"))]

    @property
    def test_python(self) -> list[str]:
        return [p for p in self.tests_files if p.endswith(".py")]

    @property
    def verifier_mode(self) -> str:
        """``separate`` or ``shared`` (Harbor's names); ``unknown`` when not declared."""
        verifier = self.config.get("verifier") or {}
        mode = str(verifier.get("environment_mode", "")).lower()
        return mode if mode in ("separate", "shared") else "unknown"


@dataclass(frozen=True)
class Rule:
    """An audit rule: metadata plus the function that finds instances of it."""

    id: str
    title: str
    classes: tuple[str, ...]
    severity: Severity
    description: str
    remedy: str
    check: Callable[[AuditTarget], Iterable[Finding]]


@dataclass
class AuditReport:
    """All findings for one target (plus optional mutation and dynamic results)."""

    target: str
    kind: str
    findings: list[Finding] = field(default_factory=list)
    mutation: dict[str, Any] | None = None

    def max_severity(self) -> Severity | None:
        return max((f.severity for f in self.findings), default=None)

    def count_at_least(self, severity: Severity) -> int:
        return sum(1 for f in self.findings if f.severity >= severity)

    def rule_ids(self) -> set[str]:
        return {f.rule_id for f in self.findings}
