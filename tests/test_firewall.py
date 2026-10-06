"""The artifact firewall returns exactly one regular file or refuses. Nothing in between."""

from __future__ import annotations

import contextlib
import gzip
import io
import tarfile
from dataclasses import dataclass

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from sealgrade.runner.firewall import (
    FirewallError,
    FirewallLimits,
    extract_single_file,
    read_stream,
)

REGULAR = (tarfile.REGTYPE, tarfile.AREGTYPE)


@dataclass(frozen=True)
class Spec:
    name: str
    kind: bytes
    data: bytes = b""
    link: str = ""


def build(specs: list[Spec]) -> bytes:
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w") as tar:
        for spec in specs:
            info = tarfile.TarInfo(spec.name)
            info.type = spec.kind
            info.linkname = spec.link
            if spec.kind in REGULAR:
                info.size = len(spec.data)
                tar.addfile(info, io.BytesIO(spec.data))
            else:
                tar.addfile(info)
    return buffer.getvalue()


def test_accepts_one_regular_file() -> None:
    assert (
        extract_single_file(
            build([Spec("solution.py", tarfile.REGTYPE, b"x = 1\n")]), "solution.py"
        )
        == b"x = 1\n"
    )


def test_accepts_empty_file() -> None:
    assert (
        extract_single_file(build([Spec("solution.py", tarfile.REGTYPE, b"")]), "solution.py")
        == b""
    )


@pytest.mark.parametrize(
    "kind",
    [
        tarfile.SYMTYPE,
        tarfile.LNKTYPE,
        tarfile.DIRTYPE,
        tarfile.CHRTYPE,
        tarfile.BLKTYPE,
        tarfile.FIFOTYPE,
    ],
)
def test_refuses_every_non_regular_entry_type(kind: bytes) -> None:
    archive = build([Spec("solution.py", kind, link="/etc/passwd")])
    with pytest.raises(FirewallError):
        extract_single_file(archive, "solution.py")


@pytest.mark.parametrize(
    "name", ["../solution.py", "/solution.py", "sub/solution.py", "other.py", "solution.py/"]
)
def test_refuses_names_that_do_not_match_exactly(name: str) -> None:
    with pytest.raises(FirewallError):
        extract_single_file(build([Spec(name, tarfile.REGTYPE, b"x")]), "solution.py")


@pytest.mark.parametrize("expected", ["", ".", "..", "a/b.py", "a\\b.py", "x\0.py"])
def test_refuses_unsafe_expected_names(expected: str) -> None:
    with pytest.raises(FirewallError):
        extract_single_file(build([Spec("solution.py", tarfile.REGTYPE, b"x")]), expected)


def test_refuses_more_than_one_entry() -> None:
    archive = build(
        [Spec("solution.py", tarfile.REGTYPE, b"x"), Spec("evil.py", tarfile.REGTYPE, b"y")]
    )
    with pytest.raises(FirewallError):
        extract_single_file(archive, "solution.py")


def test_refuses_an_empty_archive() -> None:
    with pytest.raises(FirewallError):
        extract_single_file(build([]), "solution.py")


def test_refuses_oversize_files() -> None:
    limits = FirewallLimits(max_file_bytes=10)
    with pytest.raises(FirewallError):
        extract_single_file(build([Spec("a.py", tarfile.REGTYPE, b"x" * 11)]), "a.py", limits)
    assert extract_single_file(build([Spec("a.py", tarfile.REGTYPE, b"x" * 10)]), "a.py", limits)


def test_refuses_too_many_entries_without_reading_them_all() -> None:
    limits = FirewallLimits(max_members=3)
    archive = build([Spec(f"f{i}.py", tarfile.REGTYPE, b"x") for i in range(10)])
    with pytest.raises(FirewallError):
        extract_single_file(archive, "f0.py", limits)


def test_refuses_compressed_archives() -> None:
    valid = build([Spec("solution.py", tarfile.REGTYPE, b"x")])
    with pytest.raises(FirewallError):
        extract_single_file(gzip.compress(valid), "solution.py")


def test_refuses_a_truncated_archive() -> None:
    valid = build([Spec("solution.py", tarfile.REGTYPE, b"x" * 2000)])
    with pytest.raises(FirewallError):
        extract_single_file(valid[:700], "solution.py")


def test_refuses_garbage() -> None:
    with pytest.raises(FirewallError):
        extract_single_file(b"not a tar file at all" * 100, "solution.py")


def test_read_stream_stops_at_the_limit() -> None:
    chunks = (b"x" * 1000 for _ in range(1_000_000))  # would be 1 GB if consumed
    with pytest.raises(FirewallError):
        read_stream(chunks, 10_000)


# --- property-based: the firewall's contract holds for arbitrary archives --------------------

names = st.one_of(
    st.sampled_from(
        ["solution.py", "a.py", "../solution.py", "/abs.py", "x/y.py", "", ".", "solution.py/"]
    ),
    st.text(max_size=12),
)
kinds = st.sampled_from(
    [
        tarfile.REGTYPE,
        tarfile.AREGTYPE,
        tarfile.SYMTYPE,
        tarfile.LNKTYPE,
        tarfile.DIRTYPE,
        tarfile.CHRTYPE,
        tarfile.BLKTYPE,
        tarfile.FIFOTYPE,
    ]
)
specs_st = st.builds(
    Spec,
    name=names,
    kind=kinds,
    data=st.binary(max_size=64),
    link=st.sampled_from(["", "/etc/passwd", "../x"]),
)


@settings(max_examples=300, deadline=None)
@given(specs=st.lists(specs_st, max_size=4), expected=st.sampled_from(["solution.py", "a.py"]))
def test_property_only_a_single_exact_regular_file_is_ever_returned(
    specs: list[Spec], expected: str
) -> None:
    try:
        archive = build(specs)
    except (ValueError, tarfile.TarError):  # names the tar format itself cannot encode
        return
    try:
        data = extract_single_file(archive, expected)
    except FirewallError:
        return
    assert len(specs) == 1
    spec = specs[0]
    assert spec.kind in REGULAR
    assert spec.name == expected
    assert data == spec.data


@settings(max_examples=300, deadline=None)
@given(blob=st.binary(max_size=4096))
def test_property_random_bytes_never_crash_the_firewall(blob: bytes) -> None:
    with contextlib.suppress(FirewallError):
        extract_single_file(blob, "solution.py")


@settings(max_examples=300, deadline=None)
@given(
    flips=st.lists(
        st.tuples(st.integers(min_value=0, max_value=2047), st.integers(0, 255)), max_size=6
    ),
    cut=st.one_of(st.none(), st.integers(min_value=0, max_value=2048)),
)
def test_property_corrupting_a_valid_archive_never_crashes_or_leaks(
    flips: list[tuple[int, int]], cut: int | None
) -> None:
    good = bytearray(build([Spec("solution.py", tarfile.REGTYPE, b"print('hi')\n")]))
    for position, value in flips:
        good[position % len(good)] = value
    blob = bytes(good[:cut]) if cut is not None else bytes(good)
    try:
        data = extract_single_file(blob, "solution.py")
    except FirewallError:
        return
    # If a corrupted archive still parses, it must still have yielded a bounded byte string.
    assert isinstance(data, bytes) and len(data) <= 1024 * 1024
