"""Running one untrusted or trusted phase in its own throw-away container.

Every phase follows the same pattern:

1. create the container with the policy applied and fresh volumes mounted,
2. read the *effective* configuration back and refuse to continue if it is weaker than the policy,
3. copy inputs in (the container is not running yet),
4. start it with the phase's work as the container's main process,
5. wait with a hard timeout, killing the container if it overruns.

Because the work is the main process, the container stops when it ends, and Docker kills every
process left in it. Nothing can outlive its phase.
"""

from __future__ import annotations

import contextlib
import time
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

import requests

from sealgrade.runner.docker_backend import LABEL, make_tar
from sealgrade.runner.policy import ContainerPolicy, audit_effective_config


@dataclass(frozen=True)
class Upload:
    """A file to place in a mounted volume before the phase starts."""

    data: bytes
    mode: int = 0o444
    uid: int = 0


@dataclass
class RunContext:
    """Tracks every container and volume of one grading run so they are always cleaned up."""

    cli: Any
    run_id: str
    containers: list[Any] = field(default_factory=list)
    volumes: list[Any] = field(default_factory=list)

    def new_volume(self, role: str) -> Any:
        volume = self.cli.volumes.create(name=f"{self.run_id}-{role}", labels={LABEL: "1"})
        self.volumes.append(volume)
        return volume

    def cleanup(self) -> None:
        for container in self.containers:
            with contextlib.suppress(Exception):
                container.remove(force=True)
        for volume in self.volumes:
            with contextlib.suppress(Exception):
                volume.remove(force=True)


@dataclass
class Phase:
    """The outcome of one phase. The container is stopped but not yet removed."""

    name: str
    container: Any
    exit_code: int | None
    timed_out: bool
    elapsed_sec: float
    logs_tail: str


def run_phase(
    ctx: RunContext,
    *,
    name: str,
    image: str,
    command: Sequence[str],
    policy: ContainerPolicy,
    mounts: Mapping[str, str],
    uploads: Mapping[str, Mapping[str, Upload]],
    env: Mapping[str, str] | None = None,
    timeout_sec: int,
) -> Phase:
    """Run ``command`` in a fresh, policy-restricted container.

    ``mounts`` maps a path inside the container to a volume role (a fresh volume is created);
    ``uploads`` maps such a path to the files to place there before starting.
    """
    volumes = {
        ctx.new_volume(role).name: {"bind": path, "mode": "rw"} for path, role in mounts.items()
    }
    kwargs = policy.create_kwargs()
    if env:
        kwargs["environment"] = {**kwargs["environment"], **dict(env)}
    container = ctx.cli.containers.create(
        image,
        command=list(command),
        name=f"{ctx.run_id}-{name}",
        labels={LABEL: "1"},
        volumes=volumes,
        working_dir="/work" if "/work" in mounts else "/",
        **kwargs,
    )
    ctx.containers.append(container)

    audit_effective_config(ctx.cli.api.inspect_container(container.id), policy, list(volumes))

    for path, files in uploads.items():
        by_owner: dict[int, dict[str, Upload]] = {}
        for rel, upload in files.items():
            by_owner.setdefault(upload.uid, {})[rel] = upload
        for uid, group in by_owner.items():
            by_mode: dict[int, dict[str, bytes]] = {}
            for rel, upload in group.items():
                by_mode.setdefault(upload.mode, {})[rel] = upload.data
            for mode, payload in by_mode.items():
                container.put_archive(path, make_tar(payload, uid=uid, gid=uid, mode=mode))

    started = time.monotonic()
    container.start()
    timed_out = False
    exit_code: int | None = None
    try:
        exit_code = int(container.wait(timeout=timeout_sec)["StatusCode"])
    except (requests.exceptions.ReadTimeout, requests.exceptions.ConnectionError):
        timed_out = True
        with contextlib.suppress(Exception):
            container.kill()
        with contextlib.suppress(Exception):
            container.wait(timeout=10)
    elapsed = time.monotonic() - started
    try:
        logs = container.logs(tail=15).decode("utf-8", errors="replace")
    except Exception:
        logs = ""
    return Phase(name, container, exit_code, timed_out, elapsed, logs.strip())
