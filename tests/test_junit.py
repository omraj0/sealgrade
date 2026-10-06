from __future__ import annotations

import pytest

from sealgrade.runner.junit import JunitError, parse_junit


def report(tests: int = 3, failures: int = 0, errors: int = 0, skipped: int = 0) -> bytes:
    cases = []
    for i in range(tests):
        inner = ""
        if i < failures:
            inner = "<failure message='x'/>"
        elif i < failures + errors:
            inner = "<error message='x'/>"
        elif i < failures + errors + skipped:
            inner = "<skipped message='x'/>"
        cases.append(f"<testcase classname='c' name='t{i}'>{inner}</testcase>")
    body = "".join(cases)
    suite = (
        f"<testsuite name='pytest' tests='{tests}' failures='{failures}' "
        f"errors='{errors}' skipped='{skipped}'>{body}</testsuite>"
    )
    return f"<?xml version='1.0'?><testsuites>{suite}</testsuites>".encode()


def test_a_clean_report_parses() -> None:
    totals = parse_junit(report(5))
    assert (totals.tests, totals.failures, totals.errors, totals.skipped) == (5, 0, 0, 0)
    assert totals.clean


@pytest.mark.parametrize("kwargs", [{"failures": 1}, {"errors": 1}, {"skipped": 2}])
def test_failures_errors_and_skips_are_not_clean(kwargs: dict[str, int]) -> None:
    assert not parse_junit(report(4, **kwargs)).clean


def test_a_bare_testsuite_root_is_accepted() -> None:
    data = b"<testsuite tests='1' failures='0' errors='0'><testcase name='a'/></testsuite>"
    assert parse_junit(data).tests == 1


@pytest.mark.parametrize(
    "data",
    [
        b"",
        b"not xml",
        b"<testsuites/>",  # no testsuite
        b"<!DOCTYPE x [<!ENTITY a 'b'>]><testsuites><testsuite tests='0'/></testsuites>",
        b"<!doctype x><testsuites><testsuite tests='0'/></testsuites>",
        b"<testsuite tests='abc'/>",
        b"<testsuite tests='-1'/>",
        # attributes that do not match the elements they summarise
        b"<testsuite tests='5' failures='0' errors='0'><testcase name='a'/></testsuite>",
        b"<testsuite tests='1' failures='0' errors='0'>"
        b"<testcase name='a'><failure/></testcase></testsuite>",
    ],
)
def test_malformed_or_inconsistent_reports_are_refused(data: bytes) -> None:
    with pytest.raises(JunitError):
        parse_junit(data)


def test_entity_expansion_bombs_are_refused_before_parsing() -> None:
    bomb = (
        b'<?xml version="1.0"?><!DOCTYPE lolz [<!ENTITY lol "lol">'
        b'<!ENTITY lol2 "&lol;&lol;&lol;&lol;&lol;&lol;&lol;&lol;&lol;&lol;">]>'
        b"<testsuite tests='0'>&lol2;</testsuite>"
    )
    with pytest.raises(JunitError):
        parse_junit(bomb)
