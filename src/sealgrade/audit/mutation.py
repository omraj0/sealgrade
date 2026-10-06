"""Mutation testing for verifiers: how many plausible bugs does the task's ground truth catch?

Take the reference solution, introduce one small, plausible bug at a time (flip an operator, tweak
a constant, drop a statement ...), and grade each mutant against the task's cases. A mutant that
still passes everything is a **survivor**: either an equivalent program (nothing to detect) or a
gap in the tests. The *mutation score* is killed / (killed + survived).

Mutants are generated deterministically; when there are more than ``max_mutants`` a seeded sample is
taken so the same task always yields the same report. Survivors are listed for a human to review,
because telling an equivalent mutant from a real gap is undecidable in general.
"""

from __future__ import annotations

import ast
import copy
import difflib
import random
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from typing import Any

from sealgrade.audit.local import LocalResult, grade_locally
from sealgrade.spec.task import TaskSpec

_BINOP_SWAP: dict[type[ast.operator], type[ast.operator]] = {
    ast.Add: ast.Sub,
    ast.Sub: ast.Add,
    ast.Mult: ast.Add,
    ast.FloorDiv: ast.Mult,
    ast.Div: ast.Mult,
    ast.Mod: ast.Mult,
}
_CMP_SWAP: dict[type[ast.cmpop], type[ast.cmpop]] = {
    ast.Lt: ast.LtE,
    ast.LtE: ast.Lt,
    ast.Gt: ast.GtE,
    ast.GtE: ast.Gt,
    ast.Eq: ast.NotEq,
    ast.NotEq: ast.Eq,
    ast.In: ast.NotIn,
    ast.NotIn: ast.In,
    ast.Is: ast.IsNot,
    ast.IsNot: ast.Is,
}


@dataclass(frozen=True)
class Site:
    """One place a mutation can be applied: the node's position in a pre-order walk."""

    index: int
    operator: str
    line: int


@dataclass(frozen=True)
class MutantResult:
    operator: str
    line: int
    status: str  # killed | survived | invalid
    diff: str = ""


@dataclass
class MutationReport:
    task: str
    total: int = 0
    killed: int = 0
    survived: int = 0
    invalid: int = 0
    survivors: list[MutantResult] = field(default_factory=list)

    @property
    def score(self) -> float:
        valid = self.killed + self.survived
        return 1.0 if valid == 0 else self.killed / valid

    def as_dict(self) -> dict[str, object]:
        return {
            "task": self.task,
            "mutants": self.total,
            "killed": self.killed,
            "survived": self.survived,
            "invalid": self.invalid,
            "score": round(self.score, 4),
            "survivors": [
                {"operator": s.operator, "line": s.line, "diff": s.diff} for s in self.survivors
            ],
        }


def _skippable_constants(tree: ast.AST) -> set[int]:
    """Docstrings and error-message strings: mutating them can never change behaviour."""
    skip: set[int] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Expr) and isinstance(node.value, ast.Constant):
            skip.add(id(node.value))
        if isinstance(node, ast.Raise):
            for inner in ast.walk(node):
                if isinstance(inner, ast.Constant) and isinstance(inner.value, str):
                    skip.add(id(inner))
    return skip


def _sites(tree: ast.AST) -> list[Site]:
    sites: list[Site] = []
    skip = _skippable_constants(tree)
    for index, node in enumerate(ast.walk(tree)):
        line = getattr(node, "lineno", 0)
        if isinstance(node, ast.BinOp) and type(node.op) in _BINOP_SWAP:
            sites.append(
                Site(
                    index,
                    f"arith {type(node.op).__name__}->{_BINOP_SWAP[type(node.op)].__name__}",
                    line,
                )
            )
        elif isinstance(node, ast.AugAssign) and type(node.op) in _BINOP_SWAP:
            sites.append(Site(index, f"augassign {type(node.op).__name__}", line))
        elif isinstance(node, ast.Compare) and any(type(o) in _CMP_SWAP for o in node.ops):
            sites.append(Site(index, "comparison flip", line))
        elif isinstance(node, ast.BoolOp):
            sites.append(Site(index, "and/or swap", line))
        elif isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.Not):
            sites.append(Site(index, "remove not", line))
        elif (
            isinstance(node, ast.Constant)
            and id(node) not in skip
            and not isinstance(node.value, bytes)
            and node.value is not Ellipsis
        ):
            sites.append(Site(index, f"constant {type(node.value).__name__}", line))
        elif isinstance(node, ast.Return) and node.value is not None:
            sites.append(Site(index, "return None", line))
        elif isinstance(node, ast.If):
            sites.append(Site(index, "negate condition", line))
        elif isinstance(node, (ast.Expr, ast.Assign, ast.AugAssign)) and not isinstance(
            getattr(node, "value", None), ast.Constant
        ):
            sites.append(Site(index, "delete statement", line))
        elif isinstance(node, (ast.Break, ast.Continue)):
            sites.append(Site(index, "break/continue swap", line))
    return sites


def _mutate_constant(value: Any) -> Any:
    if isinstance(value, bool):
        return not value
    if isinstance(value, int):
        return value + 1
    if isinstance(value, float):
        return value + 1.0
    if isinstance(value, str):
        return "" if value else "x"
    return value


def _apply(tree: ast.Module, site: Site) -> ast.Module | None:
    """A copy of ``tree`` with the mutation at ``site`` applied, or ``None`` if not applicable."""
    clone = copy.deepcopy(tree)
    nodes = list(ast.walk(clone))
    node = nodes[site.index]
    if isinstance(node, ast.BinOp | ast.AugAssign) and (
        isinstance(node, ast.BinOp) or site.operator.startswith("augassign")
    ):
        node.op = _BINOP_SWAP[type(node.op)]()
    elif isinstance(node, ast.Compare):
        node.ops = [_CMP_SWAP.get(type(o), type(o))() for o in node.ops]
    elif isinstance(node, ast.BoolOp):
        node.op = ast.Or() if isinstance(node.op, ast.And) else ast.And()
    elif isinstance(node, ast.UnaryOp):
        parent = next((p for p in nodes if any(c is node for c in ast.iter_child_nodes(p))), None)
        if parent is None:
            return None
        _replace_child(parent, node, node.operand)
    elif isinstance(node, ast.Constant):
        node.value = _mutate_constant(node.value)
    elif isinstance(node, ast.Return):
        node.value = ast.Constant(value=None)
    elif isinstance(node, ast.If):
        node.test = ast.UnaryOp(op=ast.Not(), operand=node.test)
    elif isinstance(node, (ast.Expr, ast.Assign, ast.AugAssign)):
        parent = next((p for p in nodes if any(c is node for c in ast.iter_child_nodes(p))), None)
        if parent is None:
            return None
        _replace_child(parent, node, ast.Pass())
    elif isinstance(node, (ast.Break, ast.Continue)):
        parent = next((p for p in nodes if any(c is node for c in ast.iter_child_nodes(p))), None)
        if parent is None:
            return None
        _replace_child(parent, node, ast.Continue() if isinstance(node, ast.Break) else ast.Break())
    ast.fix_missing_locations(clone)
    return clone


def _replace_child(parent: ast.AST, old: ast.AST, new: ast.AST) -> None:
    for name, value in ast.iter_fields(parent):
        if isinstance(value, list):
            for i, item in enumerate(value):
                if item is old:
                    value[i] = new
                    return
        elif value is old:
            setattr(parent, name, new)
            return


def _diff(original: str, mutated: str) -> str:
    lines = list(
        difflib.unified_diff(
            original.splitlines(), mutated.splitlines(), "original", "mutant", n=0, lineterm=""
        )
    )
    return "\n".join(lines[2:8])


def run_mutation(
    task: TaskSpec,
    *,
    max_mutants: int = 120,
    seed: int = 0,
    jobs: int = 4,
    grader: Callable[[TaskSpec, str], LocalResult] = grade_locally,
) -> MutationReport:
    """Mutation-test ``task``'s ground truth using its oracle solution."""
    source = task.oracle_files()[task.agent.artifacts[0]].decode("utf-8")
    tree = ast.parse(source)
    baseline = ast.unparse(tree)
    sites = _sites(tree)
    if len(sites) > max_mutants:
        sites = sorted(random.Random(seed).sample(sites, max_mutants), key=lambda s: s.index)

    def evaluate(site: Site) -> MutantResult:
        mutated = _apply(tree, site)
        if mutated is None:
            return MutantResult(site.operator, site.line, "invalid")
        try:
            text = ast.unparse(mutated)
            compile(text, "<mutant>", "exec")
        except (SyntaxError, ValueError, RecursionError):
            return MutantResult(site.operator, site.line, "invalid")
        if text == baseline:
            return MutantResult(site.operator, site.line, "invalid")  # no observable change
        result = grader(task, text)
        status = "survived" if result.all_passed else "killed"
        return MutantResult(site.operator, site.line, status, _diff(baseline, text))

    with ThreadPoolExecutor(max_workers=max(1, jobs)) as pool:
        outcomes = list(pool.map(evaluate, sites))

    report = MutationReport(task=task.id, total=len(outcomes))
    for outcome in outcomes:
        if outcome.status == "killed":
            report.killed += 1
        elif outcome.status == "survived":
            report.survived += 1
            report.survivors.append(outcome)
        else:
            report.invalid += 1
    return report
