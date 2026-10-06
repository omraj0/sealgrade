"""Attack specification.

An attack is a tiny "submission" that does NOT solve the task. It may:

* run a script in the agent's sandbox (what a hostile agent could do with a shell), and/or
* leave files in the agent's working directory (what the grader will later look at).

The success rule is deliberately simple: **if the verdict says "pass", the exploit worked**,
because by construction the payload does not solve the task.

    corpus/<id>/
      attack.toml
      agent.sh            (optional) run in the agent sandbox as its last action
      payload/...         files copied into the agent's working directory
"""

from __future__ import annotations

import re
import tomllib
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field, field_validator

from sealgrade.spec.paths import is_safe_relative
from sealgrade.spec.task import TaskSpec

# Taxonomy from BenchJack (arXiv 2605.12673), see docs/TAXONOMY.md.
_CLASS = re.compile(r"^V[1-8]$")
_ID = re.compile(r"^[a-z0-9][a-z0-9-]*$")

Outcome = Literal["exploit", "blocked"]
Kind = Literal["exploit", "probe"]
Requirement = Literal["no-raising-cases"]


class Expected(BaseModel):
    """What we claim happens on each harness tier. ``None`` = not asserted (tier not built yet)."""

    t0: Outcome | None = None
    t1: Outcome | None = None
    t2: Outcome | None = None
    t3: Outcome | None = None

    def for_tier(self, tier: str) -> Outcome | None:
        return getattr(self, tier, None)


class AttackSpec(BaseModel):
    id: str
    title: str
    summary: str
    classes: list[str] = Field(min_length=1)
    patterns: list[str] = Field(default_factory=list)
    kind: Kind = "exploit"
    requires: list[Requirement] = Field(default_factory=list)
    agent_script: str | None = None
    files: dict[str, str] = Field(default_factory=dict)
    repeat: int = Field(default=1, ge=1, le=20)
    expected: Expected = Field(default_factory=Expected)
    root: Path = Field(exclude=True)

    @field_validator("id")
    @classmethod
    def _valid_id(cls, value: str) -> str:
        if not _ID.match(value):
            raise ValueError(f"attack id must match {_ID.pattern}: {value!r}")
        return value

    @field_validator("classes")
    @classmethod
    def _valid_classes(cls, value: list[str]) -> list[str]:
        for item in value:
            if not _CLASS.match(item):
                raise ValueError(f"class must be V1..V8: {item!r}")
        return value

    @field_validator("files")
    @classmethod
    def _payload_destinations_are_relative(cls, value: dict[str, str]) -> dict[str, str]:
        for dest in value:
            if not is_safe_relative(dest):
                raise ValueError(f"payload destination must be relative to the workdir: {dest!r}")
        return value

    def applies_to(self, task: TaskSpec) -> bool:
        """Whether this attack makes sense against ``task`` (see ``requires``)."""
        return not ("no-raising-cases" in self.requires and any(c.raises for c in task.cases()))

    def script_bytes(self) -> bytes | None:
        if self.agent_script is None:
            return None
        return (self.root / self.agent_script).read_bytes()

    def payload_files(self) -> dict[str, bytes]:
        """Payload bytes by destination. Sources may live in this folder or in a sibling such as
        ``../_common``, but never outside the corpus directory."""
        corpus = self.root.parent.resolve()
        files: dict[str, bytes] = {}
        for dest, src in self.files.items():
            path = (self.root / src).resolve()
            if corpus not in path.parents:
                raise ValueError(f"{self.id}: payload source escapes the corpus: {src!r}")
            files[dest] = path.read_bytes()
        return files


def load_attack(path: Path) -> AttackSpec:
    """Load ``<path>/attack.toml``."""
    path = path.resolve()
    with (path / "attack.toml").open("rb") as handle:
        data = tomllib.load(handle)
    return AttackSpec.model_validate(
        {
            **data["attack"],
            "files": data.get("files", {}),
            "expected": data.get("expected", {}),
            "root": path,
        }
    )


def load_attacks(corpus_dir: Path) -> list[AttackSpec]:
    """Load every attack under ``corpus_dir`` (sorted by id)."""
    found = [load_attack(p.parent) for p in sorted(corpus_dir.glob("*/attack.toml"))]
    return sorted(found, key=lambda a: a.id)
