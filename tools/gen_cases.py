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


GENERATORS: dict[str, Callable[[], list[dict[str, Any]]]] = {
    "py-slugify": slugify_cases,
    "py-roman": roman_cases,
    "py-merge-intervals": merge_cases,
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
