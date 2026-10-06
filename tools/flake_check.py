"""Measure how reliable a timing-dependent attack is: run it N times on one tier and task.

python tools/flake_check.py lingering-reward-writer py-slugify t0 20
"""

from __future__ import annotations

import sys
from pathlib import Path

from sealgrade.matrix import attack_submission
from sealgrade.runner import get_harness
from sealgrade.spec import load_attacks, load_tasks

ROOT = Path(__file__).resolve().parent.parent


def main(argv: list[str]) -> int:
    attack_id, task_id, tier, runs = argv[0], argv[1], argv[2], int(argv[3])
    attack = next(a for a in load_attacks(ROOT / "corpus") if a.id == attack_id)
    task = next(t for t in load_tasks(ROOT / "tasks") if t.id == task_id)
    harness = get_harness(tier)
    submission = attack_submission(attack)
    wins = sum(1 for _ in range(runs) if harness.grade(task, submission).passed)
    print(f"{attack_id} on {task_id}/{tier}: {wins}/{runs} runs graded as a pass")
    return 0 if wins in (0, runs) else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
