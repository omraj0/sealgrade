"""Container policy for untrusted phases, and a check that Docker actually applied it.

Asking Docker for a restriction and getting it are different things (daemon defaults, API quirks,
a typo). ``audit_effective_config`` reads the container's *effective* configuration back with
``inspect`` and refuses to start anything that differs from the policy.
"""

from __future__ import annotations

from collections.abc import Collection, Mapping
from dataclasses import dataclass, field
from typing import Any


class PolicyViolation(Exception):
    """A container's effective configuration is weaker than the policy requires."""


@dataclass(frozen=True)
class ContainerPolicy:
    """Restrictions applied to every untrusted container."""

    user: str = "10001:10001"
    memory_bytes: int = 256 * 1024 * 1024
    pids_limit: int = 128
    cpus: float = 1.0
    network_mode: str = "none"
    read_only_rootfs: bool = True
    cap_drop: tuple[str, ...] = ("ALL",)
    no_new_privileges: bool = True
    tmp_size: str = "32m"
    nofile_limit: int = 256
    extra_env: Mapping[str, str] = field(default_factory=dict)

    def create_kwargs(self) -> dict[str, Any]:
        """Keyword arguments for ``containers.create`` that express this policy."""
        return {
            "user": self.user,
            "read_only": self.read_only_rootfs,
            "cap_drop": list(self.cap_drop),
            "security_opt": ["no-new-privileges:true"] if self.no_new_privileges else [],
            "network_mode": self.network_mode,
            "mem_limit": self.memory_bytes,
            "memswap_limit": self.memory_bytes,  # no swap
            "nano_cpus": int(self.cpus * 1_000_000_000),
            "pids_limit": self.pids_limit,
            "init": True,  # reaps zombies; the container dies when the main process exits
            "ipc_mode": "private",
            "privileged": False,
            "tmpfs": {"/tmp": f"rw,noexec,nosuid,nodev,size={self.tmp_size}"},
            "ulimits": [
                {"Name": "nofile", "Soft": self.nofile_limit, "Hard": self.nofile_limit},
                {"Name": "core", "Soft": 0, "Hard": 0},
            ],
            "environment": {
                "HOME": "/tmp",
                "PYTHONDONTWRITEBYTECODE": "1",
                "PYTHONUNBUFFERED": "1",
                **dict(self.extra_env),
            },
        }


def audit_effective_config(
    inspect: Mapping[str, Any], policy: ContainerPolicy, allowed_volumes: Collection[str]
) -> None:
    """Raise :class:`PolicyViolation` listing every way ``inspect`` is weaker than ``policy``."""
    config = inspect.get("Config") or {}
    host = inspect.get("HostConfig") or {}
    problems: list[str] = []

    if config.get("User") != policy.user:
        problems.append(f"user is {config.get('User')!r}, wanted {policy.user!r}")
    if bool(host.get("ReadonlyRootfs")) != policy.read_only_rootfs:
        problems.append("root filesystem read-only flag differs from policy")
    cap_drop = [str(c).upper() for c in host.get("CapDrop") or []]
    for cap in policy.cap_drop:
        if cap.upper() not in cap_drop:
            problems.append(f"capability {cap} was not dropped")
    if host.get("CapAdd"):
        problems.append(f"capabilities were added: {host.get('CapAdd')}")
    if host.get("Privileged"):
        problems.append("container is privileged")
    if host.get("NetworkMode") != policy.network_mode:
        problems.append(f"network mode is {host.get('NetworkMode')!r}")
    if policy.no_new_privileges and not any(
        str(o).startswith("no-new-privileges") for o in host.get("SecurityOpt") or []
    ):
        problems.append("no-new-privileges is not set")
    for opt in host.get("SecurityOpt") or []:
        if "unconfined" in str(opt):
            problems.append(f"security profile weakened: {opt}")
    if host.get("PidsLimit") != policy.pids_limit:
        problems.append(f"pids limit is {host.get('PidsLimit')!r}")
    memory = host.get("Memory") or 0
    if memory <= 0 or memory > policy.memory_bytes:
        problems.append("memory limit missing or too high")
    if host.get("PidMode") == "host" or host.get("IpcMode") == "host":
        problems.append("shares a namespace with the host")
    if host.get("Devices"):
        problems.append("host devices are exposed")
    if host.get("PublishAllPorts") or host.get("PortBindings"):
        problems.append("ports are published")
    allowed = set(allowed_volumes)
    # Docker lists named volumes in Binds as "name:/path[:opts]". Only the volumes we created are
    # acceptable; anything else (a host path, docker.sock, a Windows drive) is a host bind mount.
    for bind in host.get("Binds") or []:
        source = str(bind).split(":", 1)[0]
        if source not in allowed:
            problems.append(f"host bind mount present: {bind}")

    for mount in inspect.get("Mounts") or []:
        kind = mount.get("Type")
        name = mount.get("Name")
        if kind == "tmpfs" and mount.get("Destination") == "/tmp":
            continue
        if kind != "volume" or name not in allowed:
            problems.append(f"unexpected mount: type={kind!r} source={mount.get('Source')!r}")

    if problems:
        raise PolicyViolation("; ".join(problems))
