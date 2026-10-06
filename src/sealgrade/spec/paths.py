"""Path validation shared by the specs.

Paths inside containers are POSIX paths no matter which OS runs SealGrade, so they are validated
as POSIX paths. (``pathlib.Path("/etc/passwd").is_absolute()`` is False on Windows, which is
exactly the kind of platform quirk a security tool must not inherit.)
"""

from __future__ import annotations

from pathlib import PurePosixPath


def is_safe_relative(path: str) -> bool:
    """True for a non-empty, relative, traversal-free POSIX path without backslashes or NUL."""
    if not path or "\\" in path or "\0" in path:
        return False
    posix = PurePosixPath(path)
    return not posix.is_absolute() and ".." not in posix.parts and bool(posix.parts)
