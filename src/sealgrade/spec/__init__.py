"""Declarative specs: tasks (what is graded) and attacks (what tries to cheat)."""

from sealgrade.spec.attack import AttackSpec, Expected, load_attack, load_attacks
from sealgrade.spec.task import Case, TaskSpec, load_task, load_tasks

__all__ = [
    "AttackSpec",
    "Case",
    "Expected",
    "TaskSpec",
    "load_attack",
    "load_attacks",
    "load_task",
    "load_tasks",
]
