"""Loading a task directory into an :class:`AuditTarget`.

Two formats are understood:

* **SealGrade-native** tasks (``task.toml`` with ``[task]``, ``[agent]``, ``[judge]``).
* **Harbor / Terminal-Bench style** tasks (``task.toml``, ``instruction.md``,
  ``environment/Dockerfile``, ``solution/``, ``tests/test.sh``; the verifier writes its reward to
  ``/logs/verifier/reward.txt``). Harbor is public (https://github.com/harbor-framework/harbor).
  The older Terminal-Bench layout (``Dockerfile`` at the task root, ``run-tests.sh``) is read too.

Only text files below a size limit are loaded; binaries and large data are listed but not read.
"""

from __future__ import annotations

import tomllib
from pathlib import Path
from typing import Any, Literal

from sealgrade.audit.dockerfile import dockerignore_patterns, parse_dockerfile
from sealgrade.audit.model import AuditTarget

MAX_FILE_BYTES = 512 * 1024
MAX_FILES = 2000
TEXT_SUFFIXES = {
    "",
    ".py",
    ".sh",
    ".toml",
    ".md",
    ".txt",
    ".json",
    ".jsonl",
    ".yaml",
    ".yml",
    ".cfg",
    ".ini",
    ".csv",
    ".dockerfile",
    ".dockerignore",
    ".gitignore",
    ".env",
    ".rb",
    ".js",
    ".ts",
    ".c",
    ".h",
    ".cpp",
    ".java",
    ".sql",
    ".xml",
    ".bat",
    ".cmd",
    ".ps1",
}
SKIP_DIRS = {"__pycache__", ".pytest_cache", "node_modules", ".venv", ".mypy_cache"}


class TargetError(Exception):
    """The path is not a recognisable task."""


def _read_files(root: Path) -> dict[str, str]:
    files: dict[str, str] = {}
    for path in sorted(root.rglob("*")):
        if len(files) >= MAX_FILES:
            break
        if not path.is_file() or path.is_symlink():
            continue
        relative = path.relative_to(root)
        if any(part in SKIP_DIRS for part in relative.parts):
            continue
        name = path.name
        suffix = path.suffix.lower()
        if suffix not in TEXT_SUFFIXES and name not in ("Dockerfile", ".dockerignore"):
            files[relative.as_posix()] = ""  # listed, not read
            continue
        try:
            if path.stat().st_size > MAX_FILE_BYTES:
                files[relative.as_posix()] = ""
                continue
            files[relative.as_posix()] = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            files[relative.as_posix()] = ""
    return files


def _load_config(root: Path) -> dict[str, Any]:
    manifest = root / "task.toml"
    if not manifest.is_file():
        return {}
    try:
        with manifest.open("rb") as handle:
            return tomllib.load(handle)
    except (tomllib.TOMLDecodeError, OSError):
        return {}


def is_task_dir(path: Path) -> bool:
    """A directory that looks like a task in either format."""
    if not path.is_dir():
        return False
    if (path / "task.toml").is_file():
        return True
    return (path / "Dockerfile").is_file() and (
        (path / "tests").is_dir() or (path / "run-tests.sh").is_file()
    )


def find_tasks(path: Path, max_depth: int = 3) -> list[Path]:
    """``path`` itself if it is a task, otherwise the task directories below it."""
    path = path.resolve()
    if is_task_dir(path):
        return [path]
    found: list[Path] = []

    def walk(directory: Path, depth: int) -> None:
        if depth > max_depth:
            return
        for child in sorted(directory.iterdir()):
            if child.is_dir() and child.name not in SKIP_DIRS and not child.name.startswith("."):
                if is_task_dir(child):
                    found.append(child)
                else:
                    walk(child, depth + 1)

    if path.is_dir():
        walk(path, 1)
    return found


def load_target(path: Path) -> AuditTarget:
    """Read ``path`` as a task and return its normalised form."""
    root = path.resolve()
    if not is_task_dir(root):
        raise TargetError(f"{path} does not look like a task directory")
    config = _load_config(root)
    files = _read_files(root)
    kind: Literal["sealgrade", "harbor"] = (
        "sealgrade" if {"agent", "judge"} <= config.keys() else "harbor"
    )
    task_id = str((config.get("task") or {}).get("id") or root.name)

    dockerfile_path: str | None = None
    for candidate in ("environment/Dockerfile", "Dockerfile"):
        if candidate in files:
            dockerfile_path = candidate
            break
    build_context = ""
    if dockerfile_path:
        build_context = str(Path(dockerfile_path).parent).replace("\\", "/")
        build_context = "" if build_context == "." else build_context
    ignore_name = f"{build_context}/.dockerignore" if build_context else ".dockerignore"
    return AuditTarget(
        root=root,
        kind=kind,
        task_id=task_id,
        files=files,
        config=config,
        dockerfile_path=dockerfile_path,
        dockerfile=parse_dockerfile(files[dockerfile_path]) if dockerfile_path else [],
        dockerignore=dockerignore_patterns(files.get(ignore_name, "")),
        build_context=build_context,
    )
