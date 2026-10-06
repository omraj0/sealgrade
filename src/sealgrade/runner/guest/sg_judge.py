"""Trusted judge (runs in the judge container).

It holds the ground truth and compares **data** produced by the candidate. It never imports,
executes or evaluates candidate code, and it treats the candidate's output file as hostile input:
size-limited, strictly parsed (no NaN or Infinity, bounded nesting) and schema-checked. Any
malformed line fails the whole run.

Comparison is strict about types: ``True`` is not ``1``, ``1`` is not ``1.0``.
"""

from __future__ import annotations

import json
import os
from typing import Any

INBOX = os.environ.get("SG_INBOX", "/inbox")
OUTBOX = os.environ.get("SG_OUTBOX", "/outbox")
MAX_RESULT_BYTES = 8 * 1024 * 1024
MAX_DEPTH = 64
MAX_FAILURES = 10
ALLOWED_KEYS = {"i", "ok", "exc", "bad"}


class Reject(Exception):
    """The candidate's output is not acceptable data."""


def _no_constant(name: str) -> Any:
    raise Reject(f"non-finite number: {name}")


def loads(text: str) -> Any:
    try:
        return json.loads(text, parse_constant=_no_constant)
    except RecursionError as exc:
        raise Reject("nesting too deep") from exc
    except ValueError as exc:
        raise Reject(f"invalid json: {exc}") from exc


def strict_equal(a: Any, b: Any, depth: int = 0) -> bool:
    """Equality that never equates different JSON types."""
    if depth > MAX_DEPTH:
        raise Reject("nesting too deep")
    if type(a) is not type(b):
        return False
    if isinstance(a, dict):
        if a.keys() != b.keys():
            return False
        return all(strict_equal(a[key], b[key], depth + 1) for key in a)
    if isinstance(a, list):
        return len(a) == len(b) and all(
            strict_equal(x, y, depth + 1) for x, y in zip(a, b, strict=True)
        )
    return bool(a == b)


def read_results(path: str, total: int) -> dict[int, dict[str, Any]]:
    """Parse the candidate's results file; raise :class:`Reject` on anything unusual."""
    try:
        size = os.path.getsize(path)
    except OSError as exc:
        raise Reject("no results produced") from exc
    if size > MAX_RESULT_BYTES:
        raise Reject("results file too large")
    with open(path, "rb") as handle:
        raw = handle.read(MAX_RESULT_BYTES + 1)
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise Reject("results are not utf-8") from exc
    parsed: dict[int, dict[str, Any]] = {}
    for line in text.splitlines():
        if not line.strip():
            continue
        record = loads(line)
        if not isinstance(record, dict) or not record.keys() <= ALLOWED_KEYS:
            raise Reject("malformed record")
        index = record.get("i")
        if type(index) is not int or not 0 <= index < total:
            raise Reject("bad case index")
        if index in parsed:
            raise Reject("duplicate case index")
        if len(record.keys() - {"i"}) != 1:
            raise Reject("a record must carry exactly one of ok, exc, bad")
        parsed[index] = record
    return parsed


def judge_case(case: dict[str, Any], record: dict[str, Any] | None) -> str | None:
    """``None`` if the case passed, otherwise a short reason."""
    if record is None:
        return "missing"
    if "bad" in record:
        return "unserializable"
    expected_exc = case.get("raises")
    if expected_exc:
        if "exc" not in record:
            return "expected an exception"
        pairs = record["exc"]
        if not isinstance(pairs, list) or not all(
            isinstance(p, list) and len(p) == 2 and all(isinstance(s, str) for s in p)
            for p in pairs
        ):
            raise Reject("malformed exception record")
        return None if ["builtins", expected_exc] in pairs else "wrong exception"
    if "exc" in record:
        return "raised unexpectedly"
    return None if strict_equal(record["ok"], case.get("expected")) else "mismatch"


def judge(cases: list[dict[str, Any]], results_path: str) -> dict[str, Any]:
    total = len(cases)
    try:
        results = read_results(results_path, total)
        failures: list[dict[str, Any]] = []
        passed = 0
        for index, case in enumerate(cases):
            reason = judge_case(case, results.get(index))
            if reason is None:
                passed += 1
            elif len(failures) < MAX_FAILURES:
                failures.append({"i": index, "why": reason})
        return {"schema": 1, "total": total, "passed": passed, "failures": failures, "error": None}
    except Reject as exc:
        return {"schema": 1, "total": total, "passed": 0, "failures": [], "error": str(exc)[:200]}


def main() -> int:
    with open(os.path.join(INBOX, "cases.jsonl"), encoding="utf-8") as handle:
        cases = [loads(line) for line in handle if line.strip()]
    report = judge(cases, os.path.join(INBOX, "results.jsonl"))
    os.makedirs(OUTBOX, exist_ok=True)
    with open(os.path.join(OUTBOX, "verdict.json"), "w", encoding="utf-8") as handle:
        json.dump(report, handle)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
