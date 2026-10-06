"""Command line interface: ``sealgrade``."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console
from rich.table import Table

from sealgrade import __version__
from sealgrade.matrix import attack_submission, run_controls, run_matrix
from sealgrade.paths import find_root
from sealgrade.report import render_html, render_markdown
from sealgrade.runner import TIERS, get_harness
from sealgrade.runner.docker_backend import docker_available
from sealgrade.spec import load_attacks, load_tasks

app = typer.Typer(
    help="Tamper-resistant evaluation runner, exploit corpus and auditor.",
    no_args_is_help=True,
    add_completion=False,
)
console = Console()

JobsOpt = Annotated[int, typer.Option("--jobs", "-j", min=1, max=8, help="Parallel grading runs")]
TiersOpt = Annotated[str, typer.Option("--tiers", "-t", help="Comma-separated tiers, e.g. t0,t1")]


def _tiers(value: str) -> list[str]:
    tiers = [t.strip() for t in value.split(",") if t.strip()]
    unknown = [t for t in tiers if t not in TIERS]
    if unknown:
        raise typer.BadParameter(
            f"unknown tier(s) {unknown}; available: {', '.join(sorted(TIERS))}"
        )
    return tiers


def _write(path: Path, text: str) -> None:
    """Write a report with Unix line endings on every platform."""
    path.write_text(text, encoding="utf-8", newline="\n")


def _need_docker() -> None:
    if not docker_available():
        console.print(
            "[red]No Docker daemon reachable.[/red] "
            "Start Docker Desktop (or the Docker Engine) first."
        )
        raise typer.Exit(2)


@app.callback(invoke_without_command=True)
def main(
    version: Annotated[bool, typer.Option("--version", help="Show the version and exit.")] = False,
) -> None:
    if version:
        console.print(__version__)
        raise typer.Exit()


@app.command("tasks")
def list_tasks() -> None:
    """List the sample tasks."""
    table = Table("id", "title", "function", "cases")
    for task in load_tasks(find_root() / "tasks"):
        table.add_row(task.id, task.title, task.judge.function, str(len(task.cases())))
    console.print(table)


@app.command("attacks")
def list_attacks() -> None:
    """List the exploit corpus."""
    table = Table("id", "classes", "title")
    for attack in load_attacks(find_root() / "corpus"):
        table.add_row(attack.id, ", ".join(attack.classes), attack.title)
    console.print(table)


@app.command("attack")
def run_one(
    task_id: Annotated[str, typer.Argument(help="Task id")],
    attack_id: Annotated[str, typer.Argument(help="Attack id")],
    tier: Annotated[str, typer.Option("--tier", "-t")] = "t0",
) -> None:
    """Run one attack on one tier and print the verdict."""
    _need_docker()
    root = find_root()
    tasks = {t.id: t for t in load_tasks(root / "tasks")}
    attacks = {a.id: a for a in load_attacks(root / "corpus")}
    if task_id not in tasks or attack_id not in attacks:
        raise typer.BadParameter(
            "unknown task or attack id (see `sealgrade tasks` / `sealgrade attacks`)"
        )
    verdict = get_harness(_tiers(tier)[0]).grade(
        tasks[task_id], attack_submission(attacks[attack_id])
    )
    outcome = "[red]EXPLOIT[/red]" if verdict.passed else "[green]blocked[/green]"
    console.print(f"{attack_id} on {verdict.tier}: {outcome} (reward={verdict.reward})")
    if verdict.detail:
        console.print(f"[dim]{verdict.detail}[/dim]")


@app.command("controls")
def controls(tiers: TiersOpt = "t0,t1", jobs: JobsOpt = 1) -> None:
    """Check that each tier passes the oracle and fails a do-nothing and a near-miss submission."""
    _need_docker()
    tasks = load_tasks(find_root() / "tasks")
    results = run_controls(
        _tiers(tiers), tasks, progress=lambda m: console.print(f"[dim]{m}[/dim]")
    )
    bad = [r for r in results if not r.ok]
    for r in bad:
        console.print(
            f"[red]FAIL[/red] {r.control} on {r.task}/{r.tier}: "
            f"reward {r.reward}, wanted {r.expected_reward}"
        )
    console.print(f"{len(results) - len(bad)} / {len(results)} controls ok")
    raise typer.Exit(1 if bad else 0)


@app.command("matrix")
def matrix(
    tiers: TiersOpt = "t0,t1",
    out: Annotated[
        Path, typer.Option("--out", "-o", help="Directory for matrix.json / .md / .html")
    ] = Path("results"),
    check: Annotated[
        bool,
        typer.Option(
            "--check", help="Exit 1 if any result differs from the documented expectation"
        ),
    ] = False,
    no_controls: Annotated[bool, typer.Option("--no-controls")] = False,
    only_attacks: Annotated[
        str, typer.Option("--attacks", help="Comma-separated attack ids to run (default: all)")
    ] = "",
    only_tasks: Annotated[
        str, typer.Option("--tasks", help="Comma-separated task ids to run (default: all)")
    ] = "",
    jobs: JobsOpt = 1,
) -> None:
    """Run attacks on tasks for the chosen tiers and write the proof matrix."""
    _need_docker()
    root = find_root()
    all_tasks = load_tasks(root / "tasks")
    all_attacks = load_attacks(root / "corpus")
    task_filter = {s.strip() for s in only_tasks.split(",") if s.strip()}
    attack_filter = {s.strip() for s in only_attacks.split(",") if s.strip()}
    for wanted, known, label in (
        (task_filter, {t.id for t in all_tasks}, "task"),
        (attack_filter, {a.id for a in all_attacks}, "attack"),
    ):
        if wanted - known:
            raise typer.BadParameter(f"unknown {label} id(s): {sorted(wanted - known)}")
    result = run_matrix(
        _tiers(tiers),
        [t for t in all_tasks if not task_filter or t.id in task_filter],
        [a for a in all_attacks if not attack_filter or a.id in attack_filter],
        with_controls=not no_controls,
        progress=lambda m: console.print(f"[dim]{m}[/dim]"),
        jobs=jobs,
    )
    out.mkdir(parents=True, exist_ok=True)
    _write(out / "matrix.json", result.to_json())
    _write(out / "matrix.md", render_markdown(result))
    _write(out / "matrix.html", render_html(result))
    console.print(render_markdown(result))
    console.print(f"Wrote {out / 'matrix.json'}, matrix.md, matrix.html")
    if check and not result.ok:
        raise typer.Exit(1)
