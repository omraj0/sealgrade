"""Regenerate ``tasks/*/cases.jsonl`` deterministically.

Expected values come from each task's oracle solution. The seed is fixed, so running this twice
produces byte-identical files (CI checks that the committed files are up to date).

    python tools/gen_cases.py            # rewrite the files
    python tools/gen_cases.py --check    # exit 1 if a committed file is stale
"""

from __future__ import annotations

import importlib.util
import json
import random
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
SEED = 20261006


def load_oracle(task_id: str, function: str) -> Callable[..., Any]:
    path = ROOT / "tasks" / task_id / "oracle" / "solution.py"
    spec = importlib.util.spec_from_file_location(f"oracle_{task_id.replace('-', '_')}", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return getattr(module, function)  # type: ignore[no-any-return]


def dump(rows: list[dict[str, Any]]) -> str:
    return "".join(json.dumps(row, ensure_ascii=True, sort_keys=True) + "\n" for row in rows)


def slugify_cases() -> list[dict[str, Any]]:
    fn = load_oracle("py-slugify", "slugify")
    rng = random.Random(SEED)
    fixed = [
        "Hello, World!",
        "  Crème brûlée  ",
        "already-a-slug",
        "---leading and trailing---",
        "Multiple     spaces\tand\ttabs",
        "ÀÉÎÕÜ ñ ç ß",
        "100% pure_python 3.12",
        "",
        "   ",
        "!!!",
        "日本語 only",
        "Mixed 日本語 and English",
        "snake_case_to-slug",
        "UPPER lower MiXeD",
        "a",
        "-",
        "x - y",
        "emoji 🚀 launch",
        "naïve café déjà vu",
        "tabs\nand\nnewlines",
    ]
    words = [
        "alpha",
        "Beta",
        "gamma",
        "Delta",
        "épsilon",
        "zeta",
        "Ñandú",
        "théta",
        "iota",
        "kappa",
        "42",
        "7up",
    ]
    glue = [" ", "  ", "-", "_", ", ", ". ", " & ", "/", "!", "  --  "]
    rows = [{"args": [text], "expected": fn(text)} for text in fixed]
    for _ in range(40):
        parts = [rng.choice(words) for _ in range(rng.randint(1, 5))]
        text = (
            rng.choice(["", " ", "-", "!!"])
            + rng.choice(glue).join(parts)
            + rng.choice(["", " ", "-", "?!"])
        )
        rows.append({"args": [text], "expected": fn(text)})
    return rows


def roman_cases() -> list[dict[str, Any]]:
    fn = load_oracle("py-roman", "to_roman")
    rng = random.Random(SEED + 1)
    fixed = [
        1,
        2,
        3,
        4,
        5,
        6,
        9,
        10,
        14,
        19,
        39,
        40,
        49,
        90,
        99,
        400,
        444,
        500,
        900,
        1994,
        2024,
        3888,
        3999,
    ]
    sampled = sorted(rng.sample(range(1, 4000), 60))
    rows: list[dict[str, Any]] = [{"args": [n], "expected": fn(n)} for n in fixed + sampled]
    for bad in (0, -5, 4000, 10_000, 3.5, "5", None, True):
        rows.append({"args": [bad], "raises": "ValueError"})
    return rows


def merge_cases() -> list[dict[str, Any]]:
    fn = load_oracle("py-merge-intervals", "merge_intervals")
    rng = random.Random(SEED + 2)
    fixed: list[list[list[int]]] = [
        [],
        [[1, 3]],
        [[1, 3], [2, 6], [8, 10], [15, 18]],
        [[1, 4], [4, 5]],
        [[1, 3], [3, 5], [5, 7]],
        [[5, 7], [1, 2], [2, 3]],
        [[1, 10], [2, 3], [4, 5]],
        [[1, 2], [3, 4]],
        [[0, 0], [0, 0]],
        [[-5, -1], [-3, 2], [4, 6]],
        [[1, 5], [1, 5], [1, 5]],
        [[2, 3], [4, 5], [6, 7], [8, 9], [1, 10]],
    ]
    cases = list(fixed)
    for _ in range(40):
        k = rng.randint(0, 9)
        intervals = []
        for _ in range(k):
            start = rng.randint(-20, 40)
            intervals.append([start, start + rng.randint(0, 12)])
        cases.append(intervals)
    return [{"args": [c], "expected": fn(c)} for c in cases]


def _expect_raises(fn: Callable[..., Any], exc: type[BaseException], *args: Any) -> dict[str, Any]:
    """A case that must raise; checks the oracle really does so."""
    try:
        fn(*args)
    except exc:
        return {"args": list(args), "raises": exc.__name__}
    raise AssertionError(f"oracle did not raise {exc.__name__} for {args!r}")


def rle_cases() -> list[dict[str, Any]]:
    fn = load_oracle("py-rle-encode", "rle_encode")
    rng = random.Random(SEED + 3)
    fixed = ["", "a", "aaabcc", "wwwwbbbw", "AAAaaa", "  ", "éééa", "abc", "z" * 12]
    rows: list[dict[str, Any]] = [{"args": [t], "expected": fn(t)} for t in fixed]
    for _ in range(30):
        text = "".join(rng.choice("aab c") for _ in range(rng.randint(0, 20)))
        rows.append({"args": [text], "expected": fn(text)})
    for bad in ("a1", "123", "x9y", 5, None, ["a"], 3.5):
        rows.append(_expect_raises(fn, ValueError, bad))
    return rows


def brackets_cases() -> list[dict[str, Any]]:
    fn = load_oracle("py-balanced-brackets", "is_balanced")
    rng = random.Random(SEED + 4)
    fixed = [
        "",
        "()",
        "([]{})",
        "(]",
        "([)]",
        "((",
        "))",
        "a(b)c",
        "{[()]}",
        "{[(])}",
        "no brackets",
        ")(",
        "(()",
        "[({})]",
        "{{{{}}}}",
        "([{}])(",
        "x",
    ]
    rows: list[dict[str, Any]] = [{"args": [t], "expected": fn(t)} for t in fixed]
    for _ in range(40):
        text = "".join(rng.choice("()[]{}x ") for _ in range(rng.randint(0, 14)))
        rows.append({"args": [text], "expected": fn(text)})
    for bad in (5, None, ["("], True):
        rows.append(_expect_raises(fn, TypeError, bad))
    return rows


def duration_cases() -> list[dict[str, Any]]:
    fn = load_oracle("py-parse-duration", "parse_duration")
    rng = random.Random(SEED + 5)
    valid = [
        "1s",
        "90s",
        "1m",
        "1h30m",
        "2d",
        "1w",
        "1w2d3h4m5s",
        "0s",
        "007s",
        "10h",
        "3600s",
        "1d1s",
    ]
    rows: list[dict[str, Any]] = [{"args": [t], "expected": fn(t)} for t in valid]
    for _ in range(40):
        chosen = [u for u in "wdhms" if rng.random() < 0.5] or ["s"]
        text = "".join(f"{rng.randint(0, 120)}{u}" for u in chosen)
        rows.append({"args": [text], "expected": fn(text)})
    invalid = [
        "",
        "1x",
        "h",
        "1h1h",
        "30m1h",
        " 1h",
        "1.5h",
        "-1h",
        "1h 30m",
        "s",
        "1",
        "1hh",
        "hello",
    ]
    for bad in [*invalid, 5, None]:
        rows.append(_expect_raises(fn, ValueError, bad))
    return rows


def semver_cases() -> list[dict[str, Any]]:
    fn = load_oracle("py-semver-compare", "compare_versions")
    rng = random.Random(SEED + 6)
    pairs = [
        ("1.0.0", "1.0.0"),
        ("1.2.3", "1.2.4"),
        ("1.10.0", "1.9.0"),
        ("2.0.0", "1.99.99"),
        ("1.0.0-alpha", "1.0.0"),
        ("1.0.0", "1.0.0-rc1"),
        ("1.0.0-alpha", "1.0.0-beta"),
        ("1.0.0-rc1", "1.0.0-rc1"),
        ("0.0.1", "0.0.1"),
        ("10.0.0", "9.0.0"),
        ("1.0.0-b", "1.0.0-a"),
        ("1.0.0-alpha.1", "1.0.0-alpha.2"),
        ("01.2.3", "1.2.3"),
        ("0.9.9", "0.10.0"),
        ("1.2.3", "1.2.3-rc1"),
    ]
    rows: list[dict[str, Any]] = [{"args": [a, b], "expected": fn(a, b)} for a, b in pairs]

    def version() -> str:
        base = f"{rng.randint(0, 3)}.{rng.randint(0, 12)}.{rng.randint(0, 12)}"
        return base + (
            rng.choice(["-alpha", "-beta", "-rc1", "-rc2"]) if rng.random() < 0.3 else ""
        )

    for _ in range(40):
        a, b = version(), version()
        rows.append({"args": [a, b], "expected": fn(a, b)})
    for a, b in [
        ("1.0", "1.0.0"),
        ("a.b.c", "1.0.0"),
        ("1.0.0", "1.0.0.0"),
        ("1.0.0-", "1.0.0"),
        (5, "1.0.0"),
        ("1.0.0", None),
        ("v1.0.0", "1.0.0"),
    ]:
        rows.append(_expect_raises(fn, ValueError, a, b))
    return rows


def word_frequency_cases() -> list[dict[str, Any]]:
    fn = load_oracle("py-word-frequency", "word_frequency")
    rng = random.Random(SEED + 7)
    fixed = [
        "",
        "Hello hello HELLO",
        "Don't stop, don't STOP!",
        "'tis the season to be jolly",
        "a-b c_d e.f",
        "one two  two   three three three",
        "it's 'quoted' text",
        "numbers 123 are ignored",
        "O'Neil's O'neil's",
        "rock'n'roll",
        "''' ''",
        "Ünïcode wörds",
        "The the THE tHe",
    ]
    rows: list[dict[str, Any]] = [{"args": [t], "expected": fn(t)} for t in fixed]
    pool = [
        "the",
        "Cat",
        "sat",
        "on",
        "mat",
        "don't",
        "It's",
        "dog",
        "Dog",
        "run",
        "'quoted'",
        "x1",
    ]
    glue = [" ", ", ", ". ", "! ", " - ", "\n", "  "]
    for _ in range(40):
        words = [rng.choice(pool) for _ in range(rng.randint(0, 9))]
        text = "".join(w + rng.choice(glue) for w in words)
        rows.append({"args": [text], "expected": fn(text)})
    return rows


def two_sum_cases() -> list[dict[str, Any]]:
    fn = load_oracle("py-two-sum", "two_sum")
    rng = random.Random(SEED + 8)
    fixed = [
        ([2, 7, 11, 15], 9),
        ([3, 3], 6),
        ([3], 6),
        ([], 0),
        ([1, 2, 3], 7),
        ([1, 2, 3, 4], 5),
        ([0, 0], 0),
        ([-1, -2, -3, -4, -5], -8),
        ([5, 5, 5], 10),
        ([1, 5, 5, 1], 6),
        ([4], 8),
    ]
    cases = list(fixed)
    for _ in range(40):
        numbers = [rng.randint(-5, 10) for _ in range(rng.randint(0, 8))]
        cases.append((numbers, rng.randint(-5, 12)))
    return [{"args": [n, t], "expected": fn(n, t)} for n, t in cases]


def _nested(rng: random.Random, depth: int) -> list[Any]:
    return [
        _nested(rng, depth - 1) if depth > 0 and rng.random() < 0.4 else rng.randint(-9, 9)
        for _ in range(rng.randint(0, 4))
    ]


def flatten_cases() -> list[dict[str, Any]]:
    fn = load_oracle("py-flatten", "flatten")
    rng = random.Random(SEED + 9)
    fixed: list[Any] = [
        [],
        [1, 2, 3],
        [1, [2, [3, [4]]]],
        [[], [[]], [[], []]],
        [[1], [2], [3]],
        [0, [0]],
        [-1, [-2, [-3]]],
        [[[[5]]]],
    ]
    rows: list[dict[str, Any]] = [{"args": [x], "expected": fn(x)} for x in fixed]
    for _ in range(30):
        value = _nested(rng, 4)
        rows.append({"args": [value], "expected": fn(value)})
    for bad in (5, "abc", None, {"a": 1}, [1, "a"], [1, [2, None]], [True], [1.5], [[1, [2.0]]]):
        rows.append(_expect_raises(fn, TypeError, bad))
    return rows


def ipv4_cases() -> list[dict[str, Any]]:
    fn = load_oracle("py-valid-ipv4", "is_valid_ipv4")
    rng = random.Random(SEED + 10)
    fixed = [
        "0.0.0.0",
        "255.255.255.255",
        "192.168.1.1",
        "1.2.3.4",
        "10.0.0.1",
        "172.16.254.1",
        "",
        "1.2.3",
        "1.2.3.4.5",
        "256.1.1.1",
        "01.2.3.4",
        "1.2.3.04",
        "1.2.3.-4",
        " 1.2.3.4",
        "1.2.3.4 ",
        "a.b.c.d",
        "1..2.3",
        "1.2.3.",
        ".1.2.3",
        "" + chr(0xFF11) + ".2.3.4",
        "1.2.3.4a",
        "0.0.0.00",
    ]
    rows: list[dict[str, Any]] = [{"args": [t], "expected": fn(t)} for t in fixed]
    for _ in range(40):
        text = ".".join(str(rng.randint(0, 300)) for _ in range(4))
        rows.append({"args": [text], "expected": fn(text)})
    for bad in (5, None, ["1.2.3.4"]):
        rows.append(_expect_raises(fn, TypeError, bad))
    return rows


def rotate_cases() -> list[dict[str, Any]]:
    fn = load_oracle("py-matrix-rotate", "rotate_clockwise")
    rng = random.Random(SEED + 11)
    fixed: list[Any] = [
        [],
        [[1]],
        [[1, 2], [3, 4]],
        [[1, 2, 3], [4, 5, 6]],
        [[1], [2], [3]],
        [[1, 2, 3]],
        [[1, 2, 3], [4, 5, 6], [7, 8, 9]],
        [[0, 0], [0, 0]],
        [[-1, 2], [3, -4]],
    ]
    rows: list[dict[str, Any]] = [{"args": [m], "expected": fn(m)} for m in fixed]
    for _ in range(25):
        height, width = rng.randint(1, 5), rng.randint(1, 5)
        matrix = [[rng.randint(-9, 9) for _ in range(width)] for _ in range(height)]
        rows.append({"args": [matrix], "expected": fn(matrix)})
    for bad in ([[1, 2], [3]], [[1], [2, 3]], [[1, 2, 3], [4, 5]]):
        rows.append(_expect_raises(fn, ValueError, bad))
    return rows


def gcd_lcm_cases() -> list[dict[str, Any]]:
    fn = load_oracle("py-gcd-lcm", "gcd_lcm")
    rng = random.Random(SEED + 12)
    fixed = [
        (12, 18),
        (1, 1),
        (7, 13),
        (100, 10),
        (21, 6),
        (17, 17),
        (1, 99),
        (48, 180),
        (2**20, 2**10),
        (999999937, 2),
    ]
    pairs = list(fixed) + [(rng.randint(1, 500), rng.randint(1, 500)) for _ in range(40)]
    rows: list[dict[str, Any]] = [{"args": [a, b], "expected": fn(a, b)} for a, b in pairs]
    for a, b in [
        (0, 5),
        (5, 0),
        (-3, 6),
        (3, -6),
        (2.5, 5),
        ("4", 6),
        (True, 3),
        (3, None),
        (None, None),
    ]:
        rows.append(_expect_raises(fn, ValueError, a, b))
    return rows


GENERATORS: dict[str, Callable[[], list[dict[str, Any]]]] = {
    "py-slugify": slugify_cases,
    "py-roman": roman_cases,
    "py-merge-intervals": merge_cases,
    "py-rle-encode": rle_cases,
    "py-balanced-brackets": brackets_cases,
    "py-parse-duration": duration_cases,
    "py-semver-compare": semver_cases,
    "py-word-frequency": word_frequency_cases,
    "py-two-sum": two_sum_cases,
    "py-flatten": flatten_cases,
    "py-valid-ipv4": ipv4_cases,
    "py-matrix-rotate": rotate_cases,
    "py-gcd-lcm": gcd_lcm_cases,
}


def main(argv: list[str]) -> int:
    check = "--check" in argv
    stale: list[str] = []
    for task_id, generate in GENERATORS.items():
        target = ROOT / "tasks" / task_id / "cases.jsonl"
        content = dump(generate())
        if check:
            if not target.exists() or target.read_text(encoding="utf-8") != content:
                stale.append(task_id)
        else:
            target.write_text(content, encoding="utf-8", newline="\n")
            print(f"wrote {target.relative_to(ROOT)} ({content.count(chr(10))} cases)")
    if stale:
        print("stale cases.jsonl for:", ", ".join(stale), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
