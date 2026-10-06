from __future__ import annotations

import io
import tarfile

from sealgrade.runner.common import parse_reward
from sealgrade.runner.docker_backend import make_tar


def _names(blob: bytes) -> dict[str, tarfile.TarInfo]:
    with tarfile.open(fileobj=io.BytesIO(blob)) as tar:
        return {m.name: m for m in tar.getmembers()}


def test_make_tar_is_deterministic() -> None:
    files = {"b.txt": b"2", "a/x.py": b"1"}
    assert make_tar(files) == make_tar(dict(reversed(list(files.items()))))


def test_make_tar_creates_parent_directories_first() -> None:
    members = _names(make_tar({"pkg/sub/mod.py": b"x"}))
    assert members["pkg"].isdir()
    assert members["pkg/sub"].isdir()
    assert members["pkg/sub/mod.py"].isfile()


def test_make_tar_marks_only_requested_files_executable() -> None:
    members = _names(make_tar({"run.sh": b"#!/bin/sh\n", "data.txt": b"x"}, executable=["run.sh"]))
    assert members["run.sh"].mode == 0o755
    assert members["data.txt"].mode == 0o644


def test_parse_reward_rejects_anything_not_a_number_in_range() -> None:
    assert parse_reward("1\n") == 1.0
    assert parse_reward("0.5") == 0.5
    for bad in (None, "", "yes", "nan", "2", "-1", "1e9"):
        assert parse_reward(bad) == 0.0
