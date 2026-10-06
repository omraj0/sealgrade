"""Data shared by every harness tier."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol

from sealgrade.spec.task import TaskSpec


@dataclass(frozen=True)
class Submission:
    """What an agent hands over: files in its working directory plus an optional final script."""

    name: str
    files: dict[str, bytes] = field(default_factory=dict)
    script: bytes | None = None
    env: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class Verdict:
    """The result of grading one submission on one tier."""

    tier: str
    reward: float
    detail: str = ""
    elapsed_sec: float = 0.0

    @property
    def passed(self) -> bool:
        return self.reward >= 1.0


class Harness(Protocol):
    """A grading strategy. Tiers differ only in how much they trust the submission."""

    tier: str

    def grade(self, task: TaskSpec, submission: Submission) -> Verdict: ...
