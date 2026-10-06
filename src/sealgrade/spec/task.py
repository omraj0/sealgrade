"""Task specification.

A task is a directory::

    tasks/<id>/
      task.toml           what is graded and which files the agent must produce
      instruction.md      the prompt the agent sees
      cases.jsonl         the ground truth (the single source of truth for every harness tier)
      oracle/<artifact>   a reference solution, used only for controls
      near_miss/<artifact>  a plausible-but-wrong solution, used only for controls
"""

from __future__ import annotations

import json
import re
import tomllib
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator

from sealgrade.spec.paths import is_safe_relative

_IDENT = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_TASK_ID = re.compile(r"^[a-z0-9][a-z0-9-]*$")


class AgentSection(BaseModel):
    """What the (untrusted) agent is asked to produce."""

    workdir: str = "/work"
    artifacts: list[str] = Field(min_length=1)
    timeout_sec: int = Field(default=60, ge=1, le=3600)

    @field_validator("artifacts")
    @classmethod
    def _artifacts_are_safe_relative_paths(cls, value: list[str]) -> list[str]:
        for artifact in value:
            if not is_safe_relative(artifact):
                raise ValueError(
                    f"artifact path must be relative and stay inside the workdir: {artifact!r}"
                )
        return value


class JudgeSection(BaseModel):
    """How the produced artifact is graded."""

    kind: Literal["function"] = "function"
    module: str = "solution"
    function: str
    cases: str = "cases.jsonl"

    @field_validator("module", "function")
    @classmethod
    def _is_identifier(cls, value: str) -> str:
        if not _IDENT.match(value):
            raise ValueError(f"not a valid Python identifier: {value!r}")
        return value


class Case(BaseModel):
    """One graded call. Either ``expected`` or ``raises`` (an exception class name) is checked."""

    args: list[Any] = Field(default_factory=list)
    kwargs: dict[str, Any] = Field(default_factory=dict)
    expected: Any = None
    raises: str | None = None


class TaskSpec(BaseModel):
    id: str
    title: str
    instruction: str = "instruction.md"
    agent: AgentSection
    judge: JudgeSection
    root: Path = Field(exclude=True)

    @field_validator("id")
    @classmethod
    def _valid_id(cls, value: str) -> str:
        if not _TASK_ID.match(value):
            raise ValueError(f"task id must match {_TASK_ID.pattern}: {value!r}")
        return value

    # --- file helpers -------------------------------------------------------------------

    def instruction_text(self) -> str:
        return (self.root / self.instruction).read_text(encoding="utf-8")

    def cases_path(self) -> Path:
        return self.root / self.judge.cases

    def cases(self) -> list[Case]:
        out: list[Case] = []
        for number, line in enumerate(
            self.cases_path().read_text(encoding="utf-8").splitlines(), 1
        ):
            if not line.strip():
                continue
            try:
                out.append(Case.model_validate(json.loads(line)))
            except ValueError as exc:
                raise ValueError(f"{self.cases_path()}:{number}: {exc}") from exc
        if not out:
            raise ValueError(f"{self.cases_path()} has no cases")
        return out

    def _folder_files(self, folder: str) -> dict[str, bytes]:
        base = self.root / folder
        files: dict[str, bytes] = {}
        for artifact in self.agent.artifacts:
            path = base / artifact
            if not path.is_file():
                raise FileNotFoundError(f"{self.id}: missing {folder}/{artifact}")
            files[artifact] = path.read_bytes()
        return files

    def oracle_files(self) -> dict[str, bytes]:
        """The reference solution (used only for controls)."""
        return self._folder_files("oracle")

    def near_miss_files(self) -> dict[str, bytes]:
        """A plausible but wrong solution that a sound harness must reject."""
        return self._folder_files("near_miss")


def load_task(path: Path) -> TaskSpec:
    """Load ``<path>/task.toml``."""
    path = path.resolve()
    manifest = path / "task.toml"
    with manifest.open("rb") as handle:
        data = tomllib.load(handle)
    try:
        return TaskSpec.model_validate(
            {**data["task"], "agent": data["agent"], "judge": data["judge"], "root": path}
        )
    except KeyError as exc:
        raise ValueError(f"{manifest}: missing section {exc}") from exc


def load_tasks(tasks_dir: Path) -> list[TaskSpec]:
    """Load every task under ``tasks_dir`` (sorted by id)."""
    found = [load_task(p.parent) for p in sorted(tasks_dir.glob("*/task.toml"))]
    return sorted(found, key=lambda t: t.id)
