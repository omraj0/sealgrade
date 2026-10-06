"""Trusted candidate executor (runs in the candidate-execution container).

It imports the candidate, calls one function on judge-provided inputs and writes the outputs as
JSON lines. It holds **no ground truth**: the container has only the declared artifacts and the
inputs, so even a candidate that tampers with this process can do no more than choose its own
outputs.

Record format, one JSON object per input::

    {"i": 0, "ok": <json value>}                       the call returned that value
    {"i": 0, "exc": [[module, qualname], ...]}         the call raised; the exception's MRO
    {"i": 0, "bad": "unserializable"}                  the return value is not plain JSON
"""

from __future__ import annotations

import importlib
import json
import os
import signal
import sys
from typing import Any

INBOX = os.environ.get("SG_INBOX", "/inbox")
OUTBOX = os.environ.get("SG_OUTBOX", "/outbox")
MAX_MRO = 8
_HAS_ALARM = hasattr(signal, "SIGALRM")  # always true in the Linux container; absent on Windows


def _describe(exc: BaseException) -> list[list[str]]:
    names: list[list[str]] = []
    for cls in type(exc).__mro__[:MAX_MRO]:
        names.append([str(getattr(cls, "__module__", "?")), str(getattr(cls, "__qualname__", "?"))])
    return names


def _on_alarm(signum: int, frame: Any) -> None:
    raise TimeoutError("case timed out")


def _alarm(seconds: int) -> None:
    if _HAS_ALARM:
        signal.alarm(seconds)


def _read_jsonl(path: str) -> list[dict[str, Any]]:
    with open(path, encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def main() -> int:
    with open(os.path.join(INBOX, "meta.json"), encoding="utf-8") as handle:
        meta = json.load(handle)
    inputs = _read_jsonl(os.path.join(INBOX, "inputs.jsonl"))
    case_timeout = int(meta.get("case_timeout", 5))

    sys.path.insert(0, os.path.join(INBOX, "candidate"))
    load_error: BaseException | None = None
    func: Any = None
    try:
        module = importlib.import_module(meta["module"])
        func = getattr(module, meta["function"])
    except BaseException as exc:
        load_error = exc

    if _HAS_ALARM:
        signal.signal(signal.SIGALRM, _on_alarm)
    lines: list[str] = []
    for case in inputs:
        index = case["i"]
        if load_error is not None:
            record: dict[str, Any] = {"i": index, "exc": _describe(load_error)}
        else:
            _alarm(case_timeout)
            try:
                value = func(*case.get("args", []), **case.get("kwargs", {}))
                _alarm(0)
                try:
                    json.dumps(value, allow_nan=False)
                    record = {"i": index, "ok": value}
                except (TypeError, ValueError, RecursionError):
                    record = {"i": index, "bad": "unserializable"}
            except BaseException as exc:
                _alarm(0)
                record = {"i": index, "exc": _describe(exc)}
        lines.append(json.dumps(record, allow_nan=False))

    os.makedirs(OUTBOX, exist_ok=True)
    with open(os.path.join(OUTBOX, "results.jsonl"), "w", encoding="utf-8") as handle:
        handle.write("\n".join(lines) + ("\n" if lines else ""))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
