"""A strict reader for pytest's JUnit XML, used by the compat tier.

The report is written by a process that shares memory with the candidate, so it is read as hostile
input: no DOCTYPE or entity declarations (no entity-expansion tricks), bounded size (the firewall
caps it first), and the totals must be internally consistent. A report only counts as a pass if it
accounts for **exactly** the expected number of tests and none failed, errored or were skipped.
"""

from __future__ import annotations

import xml.etree.ElementTree as ET
from dataclasses import dataclass


class JunitError(Exception):
    """The report is malformed or inconsistent."""


@dataclass(frozen=True)
class JunitTotals:
    tests: int
    failures: int
    errors: int
    skipped: int

    @property
    def clean(self) -> bool:
        return self.failures == 0 and self.errors == 0 and self.skipped == 0


def _count(element: ET.Element, name: str) -> int:
    raw = element.get(name, "0")
    try:
        value = int(raw)
    except ValueError as exc:
        raise JunitError(f"non-integer {name!r}") from exc
    if value < 0:
        raise JunitError(f"negative {name!r}")
    return value


def parse_junit(data: bytes) -> JunitTotals:
    """Parse ``data`` and return the totals, or raise :class:`JunitError`."""
    upper = data.upper()
    if b"<!DOCTYPE" in upper or b"<!ENTITY" in upper:
        raise JunitError("DOCTYPE and entity declarations are not allowed")
    try:
        root = ET.fromstring(data)
    except (ET.ParseError, ValueError, RecursionError) as exc:
        raise JunitError(f"unparseable report: {type(exc).__name__}") from exc

    suites = [root] if root.tag == "testsuite" else list(root.iter("testsuite"))
    if not suites:
        raise JunitError("no testsuite element")
    tests = sum(_count(s, "tests") for s in suites)
    failures = sum(_count(s, "failures") for s in suites)
    errors = sum(_count(s, "errors") for s in suites)
    skipped = sum(_count(s, "skipped") for s in suites)

    # The attributes must agree with the elements they summarise.
    cases = list(root.iter("testcase"))
    if len(cases) != tests:
        raise JunitError("testcase elements do not match the declared total")
    bad = sum(1 for c in cases if c.find("failure") is not None)
    err = sum(1 for c in cases if c.find("error") is not None)
    skip = sum(1 for c in cases if c.find("skipped") is not None)
    if (bad, err, skip) != (failures, errors, skipped):
        raise JunitError("failure counts do not match the testcase elements")
    return JunitTotals(tests, failures, errors, skipped)
