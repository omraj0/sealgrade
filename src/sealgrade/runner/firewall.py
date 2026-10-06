"""The artifact firewall: the only way bytes cross from an untrusted container to a trusted one.

Docker's ``get_archive`` hands back a tar stream built from whatever the container's filesystem
contains. For a hostile submission that stream is attacker-controlled, so nothing in it is trusted:
not the entry type (symlinks, hard links, devices, FIFOs), not the name (``..``, absolute paths),
not the declared size, not the number of entries and not the amount of data.

``extract_single_file`` returns the bytes of exactly one regular file with exactly the expected
name, or raises :class:`FirewallError`. It never touches the host filesystem: nothing is extracted
to disk, so there is no path to traverse.
"""

from __future__ import annotations

import io
import tarfile
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import PurePosixPath

_REGULAR = {tarfile.REGTYPE, tarfile.AREGTYPE}


class FirewallError(Exception):
    """An archive or artifact was refused. The message is safe to show to a user."""


@dataclass(frozen=True)
class FirewallLimits:
    max_file_bytes: int = 1 * 1024 * 1024
    max_members: int = 16
    # Tar framing adds headers and padding; allow some overhead on top of the file limit.
    stream_overhead_bytes: int = 64 * 1024


ARTIFACT_LIMITS = FirewallLimits()
RESULT_LIMITS = FirewallLimits(max_file_bytes=8 * 1024 * 1024)
VERDICT_LIMITS = FirewallLimits(max_file_bytes=256 * 1024)


def read_stream(chunks: Iterable[bytes], limit: int) -> bytes:
    """Concatenate ``chunks``, refusing to buffer more than ``limit`` bytes."""
    buffer = bytearray()
    for chunk in chunks:
        buffer.extend(chunk)
        if len(buffer) > limit:
            raise FirewallError("archive stream exceeds the size limit")
    return bytes(buffer)


def extract_single_file(
    archive: bytes, expected_name: str, limits: FirewallLimits = ARTIFACT_LIMITS
) -> bytes:
    """Return the contents of the one regular file named ``expected_name`` inside ``archive``."""
    if (
        not expected_name
        or "/" in expected_name
        or "\\" in expected_name
        or expected_name in (".", "..")
        or "\0" in expected_name
    ):
        raise FirewallError("invalid expected name")
    try:
        # "r:" accepts only an uncompressed tar, so there is no decompression to bomb.
        with tarfile.open(fileobj=io.BytesIO(archive), mode="r:") as tar:
            members: list[tarfile.TarInfo] = []
            for member in tar:
                members.append(member)
                if len(members) > limits.max_members:
                    raise FirewallError("too many entries in archive")
            if len(members) != 1:
                raise FirewallError("expected exactly one entry in archive")
            member = members[0]
            if member.type not in _REGULAR:
                raise FirewallError("entry is not a regular file")
            if member.name != expected_name or PurePosixPath(member.name).name != expected_name:
                raise FirewallError("entry name does not match the declared artifact")
            if member.size < 0 or member.size > limits.max_file_bytes:
                raise FirewallError("file exceeds the size limit")
            handle = tar.extractfile(member)
            if handle is None:
                raise FirewallError("entry cannot be read")
            data = handle.read(limits.max_file_bytes + 1)
    except FirewallError:
        raise
    except (tarfile.TarError, EOFError, OSError, ValueError, OverflowError) as exc:
        raise FirewallError(f"malformed archive: {type(exc).__name__}") from exc
    if len(data) != member.size or len(data) > limits.max_file_bytes:
        raise FirewallError("declared size does not match the data")
    return data


def fetch_file(
    container: object, path: str, limits: FirewallLimits = ARTIFACT_LIMITS
) -> bytes | None:
    """Copy one file out of a (stopped) container through the firewall.

    Returns ``None`` if the file does not exist; raises :class:`FirewallError` if it exists but is
    not acceptable. Only the single named path is requested, never a directory.
    """
    from docker.errors import NotFound

    from sealgrade.runner.docker_backend import retry_docker

    expected_name = PurePosixPath(path).name
    try:
        stream, _stat = retry_docker(lambda: container.get_archive(path))  # type: ignore[attr-defined]
    except NotFound:
        return None
    archive = read_stream(stream, limits.max_file_bytes + limits.stream_overhead_bytes)
    return extract_single_file(archive, expected_name, limits)
