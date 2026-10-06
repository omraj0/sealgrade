"""A thin, dependency-contained wrapper around the Docker Engine API."""

from __future__ import annotations

import io
import shlex
import tarfile
import time
import uuid
from collections.abc import Iterable, Mapping
from pathlib import PurePosixPath
from typing import Any

import docker
from docker.errors import APIError, DockerException

LABEL = "io.sealgrade.managed"
DAEMON_TIMEOUT_SEC = 180  # per API call; never wait forever on a stuck daemon


def retry_docker(call: Any, *, attempts: int = 4, base_delay: float = 0.5) -> Any:
    """Run an *idempotent* Docker API call, retrying transient server errors (HTTP 5xx).

    Docker Desktop occasionally answers 500 under sustained load. Retrying is only safe for calls
    that have no side effect until they succeed (creating an exec, copying files, starting a
    container), so this is applied selectively, never to running a command.
    """
    for attempt in range(1, attempts + 1):
        try:
            return call()
        except APIError as exc:
            status = exc.status_code or 0
            if status < 500 or attempt == attempts:
                raise
            time.sleep(base_delay * attempt)
    raise AssertionError("unreachable")


def client() -> Any:
    """A Docker client from the environment (DOCKER_HOST, Docker Desktop pipe, ...)."""
    return docker.from_env(timeout=DAEMON_TIMEOUT_SEC)


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
    mode: int = 0o644,
) -> bytes:
    """Build a tar stream for ``put_archive``, including parent directories.

    Files get ``mode`` (or 0o755 if listed in ``executable``) and are owned by ``uid:gid``.
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
            info.mode = 0o755 if name in exec_set else mode
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
        archive = make_tar(files, executable=executable)
        retry_docker(lambda: container.put_archive(dest_dir, archive))


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
    api = container.client.api
    exec_id = retry_docker(
        lambda: api.exec_create(
            container.id, command, user=user, workdir=workdir, environment=dict(env or {})
        )
    )["Id"]
    raw = api.exec_start(exec_id)
    output = raw.decode("utf-8", errors="replace") if raw else ""
    exit_code = api.exec_inspect(exec_id).get("ExitCode")
    return int(exit_code if exit_code is not None else -1), output


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
