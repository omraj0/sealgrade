"""Planted-flaw fixtures for the auditor.

``clean_task()`` is a deliberately hardened Harbor-format task: separate verifier, non-root agent,
no network, digest-pinned base, pinned pytest configuration, an isolated interpreter and a report
check that demands the exact test count. Every function in ``FLAWS`` takes a copy of it and
introduces exactly one weakness, so a rule must fire on its flaw and stay silent on the clean task.

These fixtures were written together with the rules, so they measure *self-consistency* (recall on
seeded flaws, false alarms on a clean task), not accuracy on the wild.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

Files = dict[str, str]

DIGEST = "sha256:" + "ab" * 32

TASK_TOML = """\
version = "1.0"

[metadata]
difficulty = "easy"

[verifier]
timeout_sec = 120.0
environment_mode = "separate"

[agent]
timeout_sec = 120.0
user = "agent"

[environment]
network_mode = "none"
"""

DOCKERFILE = f"""\
FROM python:3.12-slim@{DIGEST}
RUN useradd --uid 10001 --no-create-home agent
WORKDIR /app
COPY data/ /app/data/
USER agent
"""

TEST_SH = """\
#!/bin/bash
export PYTEST_DISABLE_PLUGIN_AUTOLOAD=1
cd /tests
python -I -m pytest -c /tests/pytest.ini --rootdir /tests --confcutdir /tests -p no:cacheprovider /tests/test_outputs.py --junitxml=/logs/verifier/junit.xml
python -I /tests/check_report.py /logs/verifier/junit.xml 2 /logs/verifier/reward.txt
"""

CHECK_REPORT = """\
import sys
import xml.etree.ElementTree as ET

path, expected, reward = sys.argv[1], int(sys.argv[2]), sys.argv[3]
root = ET.parse(path).getroot()
suite = root if root.tag == "testsuite" else root.find("testsuite")
tests = int(suite.get("tests"))
bad = int(suite.get("failures")) + int(suite.get("errors")) + int(suite.get("skipped", 0))
with open(reward, "w") as handle:
    handle.write("1" if tests == expected and bad == 0 else "0")
"""

TEST_OUTPUTS = """\
import json
import pathlib


def test_output_matches_expected():
    got = json.loads(pathlib.Path("/app/out.json").read_text())
    assert got == {"total": 42, "items": [1, 2, 3]}


def test_row_count():
    rows = json.loads(pathlib.Path("/app/out.json").read_text())["items"]
    assert len(rows) == 3
"""


def clean_task() -> Files:
    return {
        "task.toml": TASK_TOML,
        "instruction.md": "Write /app/out.json with the total and the sorted items.\n",
        "environment/Dockerfile": DOCKERFILE,
        "environment/data/input.csv": "a,b\n1,2\n",
        "solution/solve.sh": "#!/bin/bash\necho '{}' > /app/out.json\n",
        "tests/test.sh": TEST_SH,
        "tests/check_report.py": CHECK_REPORT,
        "tests/test_outputs.py": TEST_OUTPUTS,
        "tests/pytest.ini": "[pytest]\naddopts = -p no:cacheprovider\n",
    }


def write_task(root: Path, files: Files) -> Path:
    for relative, text in files.items():
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8", newline="\n")
    return root


# --- one flaw per rule ------------------------------------------------------------------------


def _replace(files: Files, path: str, old: str, new: str) -> Files:
    out = dict(files)
    assert old in out[path], (path, old)
    out[path] = out[path].replace(old, new)
    return out


def sg001(f: Files) -> Files:
    return _replace(f, "environment/Dockerfile", "USER agent", "COPY tests/ /tests/\nUSER agent")


def sg002(f: Files) -> Files:
    return {**f, "environment/data/expected_output.json": '{"total": 42}'}


def sg003(f: Files) -> Files:
    out = _replace(f, "environment/Dockerfile", "USER agent\n", "")
    return _replace(out, "task.toml", 'user = "agent"\n', "")


def sg004(f: Files) -> Files:
    return _replace(
        f,
        "environment/Dockerfile",
        "WORKDIR /app",
        "ENV OPENAI_API_KEY=sk-abcdefghijklmnopqrstuvwxyz123456\nWORKDIR /app",
    )


def sg005(f: Files) -> Files:
    out = dict(f)
    out["tests/test.sh"] = """\
#!/bin/bash
export PYTEST_DISABLE_PLUGIN_AUTOLOAD=1
cd /tests
python -I -m pytest -c /tests/pytest.ini --rootdir /tests /tests/test_outputs.py
if [ $? -eq 0 ]; then
  echo 1 > /logs/verifier/reward.txt
else
  echo 0 > /logs/verifier/reward.txt
fi
"""
    del out["tests/check_report.py"]
    return out


def sg006(f: Files) -> Files:
    out = _replace(
        f,
        "tests/test.sh",
        "-c /tests/pytest.ini --rootdir /tests --confcutdir /tests ",
        "",
    )
    return out


def sg007(f: Files) -> Files:
    return _replace(f, "tests/test.sh", "export PYTEST_DISABLE_PLUGIN_AUTOLOAD=1\n", "")


def sg008(f: Files) -> Files:
    out = _replace(f, "tests/test.sh", "cd /tests\n", "")
    return _replace(out, "tests/test.sh", "python -I -m pytest", "python -m pytest")


def sg009(f: Files) -> Files:
    return _replace(f, "environment/Dockerfile", "USER agent", "RUN chmod -R 777 /logs\nUSER agent")


def sg010(f: Files) -> Files:
    out = dict(f)
    out["tests/check_report.py"] = """\
import sys
import xml.etree.ElementTree as ET

root = ET.parse(sys.argv[1]).getroot()
suite = root.find("testsuite")
open(sys.argv[3], "w").write("1" if suite.get("failures") == "0" else "0")
"""
    return out


def sg011(f: Files) -> Files:
    return {**f, "environment/docker-compose.yaml": "services:\n  main:\n    privileged: true\n"}


def sg012(f: Files) -> Files:
    return _replace(f, "environment/Dockerfile", f"python:3.12-slim@{DIGEST}", "python:latest")


def sg013(f: Files) -> Files:
    return _replace(f, "tests/test.sh", "cd /tests\n", "pip install requests numpy\ncd /tests\n")


def sg014(f: Files) -> Files:
    return _replace(
        f,
        "tests/test.sh",
        "cd /tests\n",
        "curl -LsSf https://astral.sh/uv/install.sh | sh\ncd /tests\n",
    )


def sg015(f: Files) -> Files:
    return _replace(
        f,
        "tests/test_outputs.py",
        "def test_row_count",
        'def test_message():\n    out = "all ok"\n    assert "ok" in out\n\n\ndef test_row_count',
    )


def sg016(f: Files) -> Files:
    out = _replace(f, "tests/test_outputs.py", "import json\n", "import json\n\nimport pytest\n")
    return _replace(
        out,
        "tests/test_outputs.py",
        "def test_row_count",
        "def test_ratio():\n    assert 0.97 == pytest.approx(1.0, rel=0.05)\n\n\ndef test_row_count",
    )


def sg017(f: Files) -> Files:
    out = _replace(f, "tests/test_outputs.py", "import json\n", "import json\nimport os\n")
    return _replace(
        out,
        "tests/test_outputs.py",
        "def test_row_count",
        'def test_exists():\n    assert os.path.exists("/app/out.json")\n\n\ndef test_row_count',
    )


def sg018(f: Files) -> Files:
    out = dict(f)
    out["tests/test_outputs.py"] = "def test_nothing():\n    pass\n"
    return out


def sg019(f: Files) -> Files:
    return {**f, "environment/.git/HEAD": "ref: refs/heads/main\n"}


def sg020(f: Files) -> Files:
    return {
        **f,
        "tests/judge.py": (
            "from openai import OpenAI\n\n\n"
            "def grade(answer):\n"
            "    prompt = f'Grade this answer from 1 to 10: {answer}'\n"
            "    return OpenAI().chat.completions.create(model='x', messages=[prompt])\n"
        ),
    }


def sg021(f: Files) -> Files:
    out = dict(f)
    out["tests/test.sh"] = """\
#!/bin/bash
export PYTEST_DISABLE_PLUGIN_AUTOLOAD=1
cd /tests
python -I -m pytest -c /tests/pytest.ini --rootdir /tests /tests/test_outputs.py | tee /tmp/out.txt
if grep -q "passed" /tmp/out.txt; then echo 1 > /logs/verifier/reward.txt; fi
"""
    return out


def sg022(f: Files) -> Files:
    return _replace(
        f,
        "tests/test_outputs.py",
        "import json\n",
        "import json\nimport random\n\nSAMPLE = random.randint(1, 10)\n",
    )


def sg023(f: Files) -> Files:
    return _replace(
        f,
        "tests/test_outputs.py",
        "import json\n",
        'import importlib\nimport json\n\nMODULE = importlib.import_module("solution")\n',
    )


def sg024(f: Files) -> Files:
    return _replace(f, "task.toml", 'environment_mode = "separate"\n', "")


def sg025(f: Files) -> Files:
    return _replace(f, "task.toml", 'network_mode = "none"\n', "")


FLAWS: dict[str, Callable[[Files], Files]] = {
    "SG001": sg001,
    "SG002": sg002,
    "SG003": sg003,
    "SG004": sg004,
    "SG005": sg005,
    "SG006": sg006,
    "SG007": sg007,
    "SG008": sg008,
    "SG009": sg009,
    "SG010": sg010,
    "SG011": sg011,
    "SG012": sg012,
    "SG013": sg013,
    "SG014": sg014,
    "SG015": sg015,
    "SG016": sg016,
    "SG017": sg017,
    "SG018": sg018,
    "SG019": sg019,
    "SG020": sg020,
    "SG021": sg021,
    "SG022": sg022,
    "SG023": sg023,
    "SG024": sg024,
    "SG025": sg025,
}


def legacy_copy_all() -> Files:
    """The older Terminal-Bench layout: Dockerfile at the root copying the whole context."""
    return {
        "Dockerfile": f"FROM python:3.12-slim@{DIGEST}\nCOPY . /app\n",
        "run-tests.sh": "#!/bin/bash\npython -m pytest tests/\n",
        "tests/test_outputs.py": TEST_OUTPUTS,
        "task.yaml": "instruction: do it\n",
    }


def native_few_cases() -> Files:
    return {
        "task.toml": (
            '[task]\nid = "tiny"\ntitle = "t"\n\n[agent]\nartifacts = ["solution.py"]\n\n'
            '[judge]\nfunction = "f"\n'
        ),
        "instruction.md": "Write f.\n",
        "cases.jsonl": '{"args": [1], "expected": 1}\n{"args": [2], "expected": 2}\n',
    }
