"""Image and test files for the compat tier (T2): hardened pytest-in-a-container.

The compat tier exists for tasks whose tests must import the candidate. It keeps the strong parts
of the strict tier (isolated agent phase, firewall, non-root read-only no-network containers) but
the candidate and the tests share one Python process, and the ground truth sits in the same
container. That residual risk is the point of having the tier: the matrix shows what it leaves
open.
"""

from __future__ import annotations

from typing import Any

from docker.errors import ImageNotFound

from sealgrade.runner.docker_backend import build_image, client
from sealgrade.runner.naive_assets import PYTEST_VERSION, context_digest, render_test_file
from sealgrade.runner.strict_assets import ensure_runtime_image
from sealgrade.spec.task import TaskSpec

# A trusted conftest: the only thing that puts the candidate on the import path.
CONFTEST = """\
import sys

sys.path.insert(0, "/inbox/candidate")
"""

# Pinned configuration; the pytest run is also told to use it explicitly (-c) and to ignore any
# other configuration file.
PYTEST_INI = """\
[pytest]
addopts = -p no:cacheprovider
testpaths = .
"""


def compat_dockerfile(runtime_tag: str) -> str:
    return f"""\
FROM {runtime_tag}
USER root
RUN pip install --no-cache-dir pytest=={PYTEST_VERSION} \\
 && (find / -xdev -perm /6000 -type f -exec chmod a-s {{}} + 2>/dev/null || true)
USER 10001:10001
"""


def compat_tag(runtime_tag: str) -> str:
    digest = context_digest({"Dockerfile": compat_dockerfile(runtime_tag).encode()})
    return f"sealgrade/compat:{digest[:12]}"


def ensure_compat_image(cli: Any | None = None) -> str:
    """Build (once) the pytest-enabled image on top of the runtime image and return its tag."""
    cli = cli or client()
    runtime = ensure_runtime_image(cli)
    tag = compat_tag(runtime)
    try:
        cli.images.get(tag)
    except ImageNotFound:
        build_image(cli, tag, {"Dockerfile": compat_dockerfile(runtime).encode()})
    return tag


def test_files(task: TaskSpec) -> dict[str, bytes]:
    """The files placed under ``/inbox/tests`` in the verification container."""
    return {
        "tests/test_task.py": render_test_file(task).encode(),
        "tests/cases.jsonl": task.cases_path().read_bytes(),
        "tests/conftest.py": CONFTEST.encode(),
        "tests/pytest.ini": PYTEST_INI.encode(),
    }


PYTEST_COMMAND = [
    "python",
    "-I",
    "-m",
    "pytest",
    "/inbox/tests/test_task.py",
    "-c",
    "/inbox/tests/pytest.ini",
    "--rootdir",
    "/inbox/tests",
    "-q",
    "--junitxml=/outbox/junit.xml",
]
