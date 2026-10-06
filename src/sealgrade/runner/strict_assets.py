"""The runtime image shared by the strict tier's agent, execution and judge containers.

One small image, built from a digest-pinned base. It contains Python, an unprivileged user, the
two trusted guest scripts and empty, correctly-owned mount points. It contains **no tests and no
ground truth**; those only ever reach the judge container at run time.
"""

from __future__ import annotations

from importlib import resources
from typing import Any

from docker.errors import ImageNotFound

from sealgrade.runner.docker_backend import build_image, client
from sealgrade.runner.naive_assets import BASE_IMAGE, context_digest

GUEST_FILES = ("sg_exec.py", "sg_judge.py")

DOCKERFILE = f"""\
FROM {BASE_IMAGE}
RUN useradd --uid 10001 --no-create-home --shell /usr/sbin/nologin agent \\
 && mkdir -p /work /inbox /outbox /opt/sg \\
 && chown 10001:10001 /work /outbox \\
 && chmod 0700 /work /outbox \\
 && chmod 0755 /inbox /opt/sg \\
 && (find / -xdev -perm /6000 -type f -exec chmod a-s {{}} + 2>/dev/null || true)
COPY guest/ /opt/sg/
RUN chmod 0555 /opt/sg/*.py
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 HOME=/tmp
WORKDIR /work
USER 10001:10001
"""


def runtime_context() -> dict[str, bytes]:
    """The image build context: the Dockerfile plus the trusted guest scripts."""
    context = {"Dockerfile": DOCKERFILE.encode()}
    guest = resources.files("sealgrade.runner.guest")
    for name in GUEST_FILES:
        context[f"guest/{name}"] = guest.joinpath(name).read_bytes()
    return context


def runtime_tag() -> str:
    return f"sealgrade/runtime:{context_digest(runtime_context())[:12]}"


def ensure_runtime_image(cli: Any | None = None) -> str:
    """Build (once per content hash) the runtime image and return its tag."""
    cli = cli or client()
    tag = runtime_tag()
    try:
        cli.images.get(tag)
    except ImageNotFound:
        build_image(cli, tag, runtime_context())
    return tag
