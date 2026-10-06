"""Measure grading latency per tier, sequentially (no parallel contention).

    python tools/bench_latency.py --runs 5 --out docs/results/latency.md

Each tier grades the oracle solution of a few tasks several times. The first run of every
(tier, task) pair is discarded as a warm-up (it can include an image build).
"""

from __future__ import annotations

import argparse
import statistics
from pathlib import Path

from sealgrade.runner import TIER_LABELS, get_harness
from sealgrade.runner.models import Submission
from sealgrade.spec import load_tasks

ROOT = Path(__file__).resolve().parent.parent
TASKS = ("py-slugify", "py-roman", "py-merge-intervals")


def percentile(values: list[float], pct: float) -> float:
    ordered = sorted(values)
    index = min(len(ordered) - 1, max(0, round(pct / 100 * (len(ordered) - 1))))
    return ordered[index]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--runs", type=int, default=5)
    parser.add_argument("--tiers", default="t0,t1,t2,t3")
    parser.add_argument("--out", type=Path, default=None)
    args = parser.parse_args()

    tasks = [t for t in load_tasks(ROOT / "tasks") if t.id in TASKS]
    rows: list[tuple[str, float, float, float, int]] = []
    for tier in args.tiers.split(","):
        harness = get_harness(tier)
        times: list[float] = []
        for task in tasks:
            submission = Submission("oracle", files=task.oracle_files())
            harness.grade(task, submission)  # warm-up, discarded
            for _ in range(args.runs):
                verdict = harness.grade(task, submission)
                assert verdict.passed, f"oracle failed on {tier}/{task.id}: {verdict.detail}"
                times.append(verdict.elapsed_sec)
        rows.append(
            (
                TIER_LABELS.get(tier, tier),
                statistics.median(times),
                percentile(times, 95),
                statistics.mean(times),
                len(times),
            )
        )
        print(f"{tier}: median {rows[-1][1]:.2f}s p95 {rows[-1][2]:.2f}s over {len(times)} runs")

    lines = [
        "| Tier | Median (s) | p95 (s) | Mean (s) | Runs |",
        "|---|---|---|---|---|",
        *[f"| {n} | {med:.2f} | {p95:.2f} | {mean:.2f} | {k} |" for n, med, p95, mean, k in rows],
    ]
    text = "\n".join(lines) + "\n"
    print(text)
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(text, encoding="utf-8", newline="\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
