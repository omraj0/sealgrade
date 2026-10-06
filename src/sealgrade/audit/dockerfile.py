"""A small, forgiving Dockerfile parser and a ``.dockerignore`` matcher.

It only needs to answer audit questions (what is copied, as which user, from which base
image), not to build anything, so it is line-oriented: comments dropped, backslash
continuations joined, instruction names upper-cased. Heredocs and exotic syntax degrade to
"unknown", never to a crash.
"""

from __future__ import annotations

import fnmatch
import re
import shlex
from pathlib import PurePosixPath

from sealgrade.audit.model import DockerInstruction


def parse_dockerfile(text: str) -> list[DockerInstruction]:
    """Parse ``text`` into logical instructions."""
    out: list[DockerInstruction] = []
    pending = ""
    pending_line = 0
    for number, raw in enumerate(text.splitlines(), 1):
        stripped = raw.strip()
        if not pending and (not stripped or stripped.startswith("#")):
            continue
        if not pending:
            pending_line = number
        if stripped.endswith("\\"):
            pending += stripped[:-1] + " "
            continue
        pending += stripped
        parts = pending.split(None, 1)
        if parts:
            out.append(
                DockerInstruction(
                    pending_line, parts[0].upper(), parts[1] if len(parts) > 1 else ""
                )
            )
        pending = ""
    if pending:
        parts = pending.split(None, 1)
        out.append(
            DockerInstruction(pending_line, parts[0].upper(), parts[1] if len(parts) > 1 else "")
        )
    return out


def copy_sources(instruction: DockerInstruction) -> list[str]:
    """The source operands of a COPY/ADD (flags like ``--chown`` removed, JSON form supported)."""
    args = instruction.args.strip()
    if args.startswith("["):
        try:
            import json

            items = json.loads(args)
        except ValueError:
            return []
        return [str(i) for i in items[:-1]]
    try:
        tokens = shlex.split(args)
    except ValueError:
        tokens = args.split()
    tokens = [t for t in tokens if not t.startswith("--")]
    return tokens[:-1]


def final_user(instructions: list[DockerInstruction]) -> str | None:
    """The user the image runs as: the last ``USER`` instruction, or ``None`` (meaning root)."""
    users = [
        i.args.split(":")[0].strip() for i in instructions if i.op == "USER" and i.args.strip()
    ]
    return users[-1] if users else None


def base_images(instructions: list[DockerInstruction]) -> list[str]:
    """Image references of every ``FROM`` (the ``AS name`` suffix and flags removed)."""
    refs: list[str] = []
    for instruction in instructions:
        if instruction.op != "FROM":
            continue
        tokens = [t for t in instruction.args.split() if not t.startswith("--")]
        if tokens:
            refs.append(tokens[0])
    return refs


_DIGEST = re.compile(r"@sha256:[0-9a-f]{64}")


def image_pin(reference: str) -> str:
    """How well ``reference`` is pinned: ``digest``, ``tag`` or ``latest``."""
    if _DIGEST.search(reference):
        return "digest"
    name = reference.rsplit("/", 1)[-1]
    if ":" not in name:
        return "latest"
    tag = name.split(":", 1)[1]
    return "latest" if tag == "latest" else "tag"


def dockerignore_patterns(text: str) -> list[str]:
    return [line.strip() for line in text.splitlines() if line.strip() and not line.startswith("#")]


def ignored(path: str, patterns: list[str]) -> bool:
    """Whether ``path`` (relative, POSIX) is excluded by ``.dockerignore`` ``patterns``.

    Supports ``*``/``?`` globs, directory patterns and ``!`` exceptions; later patterns win.
    """
    result = False
    posix = PurePosixPath(path)
    for pattern in patterns:
        negate = pattern.startswith("!")
        pat = pattern[1:] if negate else pattern
        pat = pat.lstrip("/").rstrip("/")
        hit = False
        for candidate in [str(posix), *[str(p) for p in posix.parents if str(p) != "."]]:
            if fnmatch.fnmatch(candidate, pat) or fnmatch.fnmatch(
                PurePosixPath(candidate).name, pat
            ):
                hit = True
                break
        if hit:
            result = not negate
    return result
