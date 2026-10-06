"""A thin, dependency-contained wrapper around the Docker Engine API."""

from __future__ import annotations

import io
import shlex
import tarfile
import uuid
from collections.abc import Iterable, Mapping
from pathlib import PurePosixPath
from typing import Any

import docker
from docker.errors import DockerException

LABEL = "io.sealgrade.managed"


def client() -> Any:
    """A Docker client from the environment (DOCKER_HOST, Docker Desktop pipe, ...)."""
    return docker.from_env()


def docker_available() -> bool:
    """True when a daemon answers a ping. Used to skip integration tests cleanly."""
    try:
        client().ping()
    except (DockerException, OSError):
        return False
    return True


def unique_name(prefix: str) -> str:
    return f"sg-{prefix}-{uuid.uuid4().hex[:10]}"


def make_tar(
    files: Mapping[str, bytes],
    *,
    executable: Iterable[str] = (),
    uid: int = 0,
    gid: int = 0,
) -> bytes:
    """Build a tar stream for ``put_archive``, including parent directories.

    Entries are written with a fixed mtime so the same input always yields the same bytes.
    """
    exec_set = set(executable)
    buffer = io.BytesIO()
    made_dirs: set[str] = set()
    with tarfile.open(fileobj=buffer, mode="w") as tar:
        for name in sorted(files):
            path = PurePosixPath(name)
            for parent in reversed(path.parents):
                parent_name = str(parent)
                if parent_name in (".", "") or parent_name in made_dirs:
                    continue
                made_dirs.add(parent_name)
                info = tarfile.TarInfo(parent_name)
                info.type = tarfile.DIRTYPE
                info.mode = 0o755
                info.uid, info.gid = uid, gid
                tar.addfile(info)
            data = files[name]
            info = tarfile.TarInfo(str(path))
            info.size = len(data)
            info.mode = 0o755 if name in exec_set else 0o644
            info.uid, info.gid = uid, gid
            tar.addfile(info, io.BytesIO(data))
    return buffer.getvalue()


def put_files(
    container: Any,
    dest_dir: str,
    files: Mapping[str, bytes],
    *,
    executable: Iterable[str] = (),
) -> None:
    """Copy ``files`` into ``dest_dir`` inside a running container."""
    if files:
        container.put_archive(dest_dir, make_tar(files, executable=executable))


def exec_bash(
    container: Any,
    script: str,
    *,
    timeout: int,
    user: str = "root",
    workdir: str | None = None,
    env: Mapping[str, str] | None = None,
) -> tuple[int, str]:
    """Run ``bash -c script`` in the container with a hard wall-clock limit.

    Returns ``(exit_code, combined_output)``; exit code 124 means the limit was hit.
    """
    command = ["timeout", "-k", "2", str(timeout), "bash", "-c", script]
    result = container.exec_run(command, user=user, workdir=workdir, environment=dict(env or {}))
    output = result.output.decode("utf-8", errors="replace") if result.output else ""
    return int(result.exit_code), output


def read_text(container: Any, path: str, *, tail_bytes: int | None = None) -> str | None:
    """Read a file from a running container, or ``None`` if it does not exist."""
    quoted = shlex.quote(path)
    command = f"tail -c {tail_bytes} {quoted}" if tail_bytes else f"cat {quoted}"
    code, output = exec_bash(container, command, timeout=15)
    return output if code == 0 else None


def build_image(cli: Any, tag: str, context: Mapping[str, bytes]) -> None:
    """Build an image from an in-memory context (a ``Dockerfile`` must be in ``context``)."""
    buffer = io.BytesIO(make_tar(context, executable=[n for n in context if n.endswith(".sh")]))
    buffer.seek(0)
    cli.images.build(fileobj=buffer, custom_context=True, tag=tag, rm=True, pull=False)
