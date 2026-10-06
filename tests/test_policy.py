from __future__ import annotations

import copy
from typing import Any

import pytest

from sealgrade.runner.policy import ContainerPolicy, PolicyViolation, audit_effective_config

POLICY = ContainerPolicy()
VOLUMES = ["run-work"]


def good() -> dict[str, Any]:
    """What ``docker inspect`` reports for a container that follows the policy."""
    return {
        "Config": {"User": "10001:10001"},
        "HostConfig": {
            "ReadonlyRootfs": True,
            "CapDrop": ["ALL"],
            "CapAdd": None,
            "Privileged": False,
            "NetworkMode": "none",
            "SecurityOpt": ["no-new-privileges:true"],
            "PidsLimit": POLICY.pids_limit,
            "Memory": POLICY.memory_bytes,
            "PidMode": "",
            "IpcMode": "private",
            "Devices": [],
            "PublishAllPorts": False,
            "PortBindings": {},
            "Binds": ["run-work:/work:rw"],
        },
        "Mounts": [
            {"Type": "volume", "Name": "run-work", "Destination": "/work"},
            {"Type": "tmpfs", "Destination": "/tmp"},
        ],
    }


def test_a_compliant_container_passes() -> None:
    audit_effective_config(good(), POLICY, VOLUMES)


def mutate(path: tuple[str, ...], value: Any) -> dict[str, Any]:
    data = copy.deepcopy(good())
    node = data
    for key in path[:-1]:
        node = node[key]
    node[path[-1]] = value
    return data


@pytest.mark.parametrize(
    ("data", "needle"),
    [
        (mutate(("Config", "User"), "root"), "user"),
        (mutate(("Config", "User"), ""), "user"),
        (mutate(("HostConfig", "ReadonlyRootfs"), False), "read-only"),
        (mutate(("HostConfig", "CapDrop"), []), "capability"),
        (mutate(("HostConfig", "CapAdd"), ["SYS_ADMIN"]), "added"),
        (mutate(("HostConfig", "Privileged"), True), "privileged"),
        (mutate(("HostConfig", "NetworkMode"), "bridge"), "network"),
        (mutate(("HostConfig", "NetworkMode"), "host"), "network"),
        (mutate(("HostConfig", "SecurityOpt"), []), "no-new-privileges"),
        (
            mutate(("HostConfig", "SecurityOpt"), ["no-new-privileges:true", "seccomp=unconfined"]),
            "weakened",
        ),
        (mutate(("HostConfig", "PidsLimit"), None), "pids"),
        (mutate(("HostConfig", "PidsLimit"), -1), "pids"),
        (mutate(("HostConfig", "Memory"), 0), "memory"),
        (mutate(("HostConfig", "Memory"), 10**12), "memory"),
        (mutate(("HostConfig", "PidMode"), "host"), "namespace"),
        (mutate(("HostConfig", "IpcMode"), "host"), "namespace"),
        (mutate(("HostConfig", "Devices"), [{"PathOnHost": "/dev/sda"}]), "devices"),
        (mutate(("HostConfig", "PublishAllPorts"), True), "ports"),
        (
            mutate(("HostConfig", "Binds"), ["/var/run/docker.sock:/var/run/docker.sock"]),
            "bind mount",
        ),
        (mutate(("HostConfig", "Binds"), ["C:\\Users:/work"]), "bind mount"),
        (
            mutate(("Mounts",), [{"Type": "bind", "Source": "/", "Destination": "/host"}]),
            "unexpected mount",
        ),
        (
            mutate(("Mounts",), [{"Type": "volume", "Name": "someone-elses", "Destination": "/x"}]),
            "unexpected mount",
        ),
        (mutate(("Mounts",), [{"Type": "tmpfs", "Destination": "/work"}]), "unexpected mount"),
    ],
)
def test_every_weakening_is_caught(data: dict[str, Any], needle: str) -> None:
    with pytest.raises(PolicyViolation) as caught:
        audit_effective_config(data, POLICY, VOLUMES)
    assert needle in str(caught.value).lower()


def test_all_problems_are_reported_together() -> None:
    data = mutate(("HostConfig", "Privileged"), True)
    data["Config"]["User"] = "root"
    with pytest.raises(PolicyViolation) as caught:
        audit_effective_config(data, POLICY, VOLUMES)
    assert "privileged" in str(caught.value) and "user" in str(caught.value)


def test_create_kwargs_express_the_policy() -> None:
    kwargs = POLICY.create_kwargs()
    assert kwargs["user"] == "10001:10001"
    assert kwargs["read_only"] is True
    assert kwargs["cap_drop"] == ["ALL"]
    assert kwargs["network_mode"] == "none"
    assert kwargs["privileged"] is False
    assert kwargs["pids_limit"] == POLICY.pids_limit
    assert kwargs["mem_limit"] == kwargs["memswap_limit"] == POLICY.memory_bytes
    assert "no-new-privileges:true" in kwargs["security_opt"]
    assert kwargs["tmpfs"]["/tmp"].startswith("rw,noexec,nosuid")
