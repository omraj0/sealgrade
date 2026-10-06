"""Locating the repository's ``tasks/`` and ``corpus/`` folders."""

from __future__ import annotations

import os
from pathlib import Path


def find_root(start: Path | None = None) -> Path:
    """Find the directory holding ``tasks/`` and ``corpus/``.

    Order: ``$SEALGRADE_HOME``, then the current directory and its parents.
    """
    env = os.environ.get("SEALGRADE_HOME")
    if env:
        return Path(env).resolve()
    here = (start or Path.cwd()).resolve()
    for candidate in (here, *here.parents):
        if (candidate / "tasks").is_dir() and (candidate / "corpus").is_dir():
            return candidate
    raise FileNotFoundError(
        "could not find a directory containing tasks/ and corpus/ "
        "(run from the repository root or set SEALGRADE_HOME)"
    )
