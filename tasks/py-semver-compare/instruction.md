Create `/work/solution.py` that defines `compare_versions(a: str, b: str) -> int`.

Versions look like `MAJOR.MINOR.PATCH` (three non-negative integers), optionally followed by a
pre-release tag after a hyphen, for example `1.4.2` or `2.0.0-rc1`. Return `-1` if `a` is older than
`b`, `1` if it is newer and `0` if they are equal.

Compare the three numbers numerically (`1.10.0` is newer than `1.9.0`). A version with a pre-release
tag is older than the same version without one. Two pre-release tags on the same numbers are
compared as plain strings.

Raise `ValueError` if either version is malformed or not a string.

Use only the Python standard library.
