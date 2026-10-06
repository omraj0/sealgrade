"""The trusted guest scripts, run locally (no Docker) against hostile candidates and output."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import textwrap
from importlib import resources
from pathlib import Path
from typing import Any

import pytest

from sealgrade.runner.guest import sg_judge


def _script(name: str) -> str:
    return str(resources.files("sealgrade.runner.guest").joinpath(name))


def run_exec(
    tmp_path: Path, candidate: str, inputs: list[dict[str, Any]], timeout: int = 20
) -> str | None:
    inbox, outbox = tmp_path / "inbox", tmp_path / "outbox"
    (inbox / "candidate").mkdir(parents=True)
    outbox.mkdir()
    (inbox / "candidate" / "solution.py").write_text(textwrap.dedent(candidate), encoding="utf-8")
    (inbox / "inputs.jsonl").write_text(
        "".join(json.dumps(c) + "\n" for c in inputs), encoding="utf-8"
    )
    (inbox / "meta.json").write_text(
        json.dumps({"module": "solution", "function": "f", "case_timeout": 2}), encoding="utf-8"
    )
    env = {**os.environ, "SG_INBOX": str(inbox), "SG_OUTBOX": str(outbox)}
    subprocess.run(
        [sys.executable, "-I", _script("sg_exec.py")],
        env=env,
        timeout=timeout,
        check=False,
        capture_output=True,
    )
    results = outbox / "results.jsonl"
    return results.read_text(encoding="utf-8") if results.exists() else None


def run_judge(
    tmp_path: Path, cases: list[dict[str, Any]], results: str | bytes | None
) -> dict[str, Any]:
    inbox, outbox = tmp_path / "jin", tmp_path / "jout"
    inbox.mkdir(parents=True)
    outbox.mkdir()
    (inbox / "cases.jsonl").write_text(
        "".join(json.dumps(c) + "\n" for c in cases), encoding="utf-8"
    )
    if results is not None:
        data = results.encode() if isinstance(results, str) else results
        (inbox / "results.jsonl").write_bytes(data)
    env = {**os.environ, "SG_INBOX": str(inbox), "SG_OUTBOX": str(outbox)}
    subprocess.run(
        [sys.executable, "-I", _script("sg_judge.py")],
        env=env,
        timeout=30,
        check=True,
        capture_output=True,
    )
    report: dict[str, Any] = json.loads((outbox / "verdict.json").read_text(encoding="utf-8"))
    return report


def case(i: int, *args: Any) -> dict[str, Any]:
    return {"i": i, "args": list(args), "kwargs": {}}


# --- sg_exec ---------------------------------------------------------------------------------


def test_exec_returns_outputs_and_exceptions(tmp_path: Path) -> None:
    out = run_exec(
        tmp_path,
        """
        def f(x):
            if x < 0:
                raise ValueError("neg")
            return x * 2
        """,
        [case(0, 2), case(1, -1)],
    )
    assert out is not None
    first, second = (json.loads(line) for line in out.splitlines())
    assert first == {"i": 0, "ok": 4}
    assert second["i"] == 1 and ["builtins", "ValueError"] in second["exc"]


def test_exec_flags_unserializable_and_non_finite_values(tmp_path: Path) -> None:
    out = run_exec(
        tmp_path,
        """
        def f(x):
            return {"nan": float("nan")} if x == 0 else object()
        """,
        [case(0, 0), case(1, 1)],
    )
    assert out is not None
    records = [json.loads(line) for line in out.splitlines()]
    assert records == [{"i": 0, "bad": "unserializable"}, {"i": 1, "bad": "unserializable"}]


def test_exec_import_error_fails_every_case_but_still_reports(tmp_path: Path) -> None:
    out = run_exec(tmp_path, "raise RuntimeError('boom at import')", [case(0, 1), case(1, 2)])
    assert out is not None
    records = [json.loads(line) for line in out.splitlines()]
    assert all("exc" in r for r in records) and len(records) == 2


def test_exec_exiting_during_import_produces_no_results(tmp_path: Path) -> None:
    assert run_exec(tmp_path, "import os\nos._exit(0)\n", [case(0, 1)]) is None


# --- sg_judge: strict, type-aware comparison -------------------------------------------------


@pytest.mark.parametrize(
    ("a", "b", "equal"),
    [
        (1, 1, True),
        (True, 1, False),  # bool is not an int
        (1, 1.0, False),  # int is not a float
        ("1", 1, False),
        (None, False, False),
        ([1, 2], [1, 2], True),
        ([1, 2], [2, 1], False),
        ({"a": 1, "b": 2}, {"b": 2, "a": 1}, True),
        ({"a": 1}, {"a": 1, "b": 2}, False),
        ([True], [1], False),
        ({"k": [1, {"z": None}]}, {"k": [1, {"z": None}]}, True),
    ],
)
def test_strict_equal_never_equates_different_json_types(a: Any, b: Any, equal: bool) -> None:
    assert sg_judge.strict_equal(a, b) is equal


def test_judge_passes_a_correct_run(tmp_path: Path) -> None:
    cases = [{"expected": "a"}, {"expected": None}, {"raises": "ValueError"}]
    results = "\n".join(
        [
            json.dumps({"i": 0, "ok": "a"}),
            json.dumps({"i": 1, "ok": None}),
            json.dumps({"i": 2, "exc": [["builtins", "ValueError"], ["builtins", "Exception"]]}),
        ]
    )
    report = run_judge(tmp_path, cases, results)
    assert report["passed"] == 3 and report["total"] == 3 and report["error"] is None


def test_judge_rejects_type_confusion(tmp_path: Path) -> None:
    report = run_judge(tmp_path, [{"expected": 1}], json.dumps({"i": 0, "ok": True}))
    assert report["passed"] == 0


def test_judge_rejects_a_look_alike_exception_class(tmp_path: Path) -> None:
    fake = {"i": 0, "exc": [["solution", "ValueError"], ["builtins", "Exception"]]}
    report = run_judge(tmp_path, [{"raises": "ValueError"}], json.dumps(fake))
    assert report["passed"] == 0


def test_judge_fails_missing_cases(tmp_path: Path) -> None:
    report = run_judge(tmp_path, [{"expected": 1}, {"expected": 2}], json.dumps({"i": 0, "ok": 1}))
    assert report["passed"] == 1 and report["failures"][0]["why"] == "missing"


HOSTILE_RESULTS = [
    pytest.param('{"i": 0, "ok": NaN}', id="nan"),
    pytest.param('{"i": 0, "ok": Infinity}', id="infinity"),
    pytest.param('{"i": 0, "ok": 1}' + chr(10) + '{"i": 0, "ok": 1}', id="duplicate-index"),
    pytest.param('{"i": 9, "ok": 1}', id="index-out-of-range"),
    pytest.param('{"i": true, "ok": 1}', id="bool-index"),
    pytest.param('{"i": 0, "ok": 1, "extra": 2}', id="unknown-key"),
    pytest.param('{"i": 0}', id="empty-record"),
    pytest.param('{"i": 0, "ok": 1, "bad": "x"}', id="two-payloads"),
    pytest.param("[1, 2, 3]", id="not-an-object"),
    pytest.param("not json", id="not-json"),
    pytest.param('{"i": 0, "ok": ' + "[" * 100000 + "]" * 100000 + "}", id="absurd-nesting"),
]


@pytest.mark.parametrize("results", HOSTILE_RESULTS)
def test_judge_treats_hostile_output_as_a_failed_run_not_a_crash(
    tmp_path: Path, results: str
) -> None:
    report = run_judge(tmp_path, [{"expected": 1}], results)
    assert report["passed"] == 0
    assert report["error"] is not None


def test_judge_rejects_invalid_utf8_and_missing_files(tmp_path: Path) -> None:
    assert run_judge(tmp_path / "a", [{"expected": 1}], b"\xff\xfe\x00")["error"]
    assert run_judge(tmp_path / "b", [{"expected": 1}], None)["error"] == "no results produced"


def test_judge_rejects_oversize_results(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sg_judge, "MAX_RESULT_BYTES", 100)
    path = tmp_path / "r.jsonl"
    path.write_text('{"i": 0, "ok": "' + "x" * 500 + '"}\n')
    with pytest.raises(sg_judge.Reject):
        sg_judge.read_results(str(path), 1)
