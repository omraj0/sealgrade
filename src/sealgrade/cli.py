"""Command line interface: ``sealgrade``."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console
from rich.markup import escape
from rich.table import Table

from sealgrade import __version__
from sealgrade.audit.engine import audit_path
from sealgrade.audit.model import AuditReport, Finding, Severity
from sealgrade.audit.mutation import run_mutation
from sealgrade.audit.render import to_html, to_json
from sealgrade.audit.sarif import sarif_text
from sealgrade.audit.targets import TargetError, find_tasks, load_target
from sealgrade.matrix import attack_submission, run_controls, run_matrix
from sealgrade.paths import find_root
from sealgrade.report import matrix_svg, render_html, render_markdown
from sealgrade.runner import TIERS, get_harness
from sealgrade.runner.docker_backend import docker_available
from sealgrade.spec import load_attacks, load_task, load_tasks

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
    _write(out / "matrix.svg", matrix_svg(json.loads(result.to_json())))
    console.print(render_markdown(result))
    console.print(f"Wrote {out / 'matrix.json'}, matrix.md, matrix.html")
    if check and not result.ok:
        raise typer.Exit(1)


def _print_audit_table(reports: list[AuditReport]) -> None:
    colours = {
        Severity.HIGH: "red",
        Severity.MEDIUM: "yellow",
        Severity.LOW: "cyan",
        Severity.INFO: "dim",
    }
    for report in reports:
        console.print(f"\n[bold]{escape(report.target)}[/bold] [dim]({report.kind})[/dim]")
        if not report.findings:
            console.print("  [green]no findings[/green]")
        else:
            table = Table("severity", "rule", "finding", "where", show_lines=False)
            for f in report.findings:
                where = f"{f.path}:{f.line}" if f.line else f.path
                colour = colours[f.severity]
                table.add_row(
                    f"[{colour}]{f.severity.label}[/{colour}]",
                    f.rule_id,
                    escape(f.title),
                    escape(where),
                )
            console.print(table)
        if report.mutation:
            m = report.mutation
            console.print(
                f"  mutation score [bold]{m['score'] * 100:.1f}%[/bold] "
                f"({m['killed']} killed, {m['survived']} survived, {m['invalid']} invalid "
                f"of {m['mutants']} mutants)"
            )


@app.command("audit")
def audit(
    path: Annotated[Path, typer.Argument(help="A task directory, or a directory containing tasks")],
    fmt: Annotated[
        str, typer.Option("--format", "-f", help="table, json, sarif or html")
    ] = "table",
    out: Annotated[Path | None, typer.Option("--out", "-o", help="Write the report here")] = None,
    fail_on: Annotated[
        str,
        typer.Option("--fail-on", help="Exit 1 at or above this severity: high, medium, low, none"),
    ] = "high",
    mutation: Annotated[
        bool, typer.Option("--mutation", help="Also compute a mutation score (SealGrade tasks)")
    ] = False,
    mutants: Annotated[int, typer.Option("--mutants", min=10, max=1000)] = 120,
    dynamic: Annotated[
        str,
        typer.Option("--dynamic", help="Also run the exploit corpus on these tiers, e.g. t0,t1"),
    ] = "",
    jobs: JobsOpt = 2,
) -> None:
    """Audit task directories for the reward-hacking flaw classes (static rules, plus optional
    mutation scoring and a dynamic run of the exploit corpus)."""
    if fmt not in ("table", "json", "sarif", "html"):
        raise typer.BadParameter("format must be table, json, sarif or html")
    threshold = None if fail_on == "none" else Severity.parse(fail_on)
    try:
        reports = audit_path(path)
    except TargetError as exc:
        raise typer.BadParameter(str(exc)) from exc
    if not reports:
        console.print(f"[red]No tasks found under {path}[/red]")
        raise typer.Exit(2)

    task_dirs = {load_target(d).task_id: d for d in find_tasks(path)}
    if mutation or dynamic:
        for report in reports:
            target = load_target(task_dirs[report.target])
            if target.kind != "sealgrade":
                continue
            task = load_task(task_dirs[report.target])
            if mutation:
                result = run_mutation(task, max_mutants=mutants, jobs=jobs)
                report.mutation = result.as_dict()
                if result.score < 0.9 and result.survived:
                    report.findings.append(
                        Finding(
                            "SG027",
                            Severity.MEDIUM,
                            "Weak verifier: low mutation score",
                            f"{result.survived} of {result.killed + result.survived} plausible "
                            "bugs "
                            "in the reference solution pass every case "
                            f"({result.score * 100:.1f}% killed).",
                            "cases.jsonl",
                            0,
                            ("V6",),
                        )
                    )
            if dynamic:
                _need_docker()
                tiers = _tiers(dynamic)
                matrix_result = run_matrix(
                    tiers,
                    [task],
                    [a for a in load_attacks(find_root() / "corpus") if a.kind == "exploit"],
                    with_controls=False,
                    jobs=jobs,
                )
                for attack in matrix_result.attacks:
                    for tier in tiers:
                        if matrix_result.observed(attack.id, tier) == "exploit":
                            report.findings.append(
                                Finding(
                                    "SG028",
                                    Severity.HIGH,
                                    f"Exploit succeeds on {tier}: {attack.id}",
                                    attack.title,
                                    "",
                                    0,
                                    tuple(attack.classes),
                                )
                            )
            report.findings.sort(key=lambda f: (-int(f.severity), f.rule_id, f.path, f.line))

    if fmt == "table":
        _print_audit_table(reports)
    else:
        text = {"json": to_json, "sarif": sarif_text, "html": to_html}[fmt](reports)
        if out:
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_text(text, encoding="utf-8", newline="\n")
            console.print(f"Wrote {out}")
        else:
            typer.echo(text)
    if fmt == "table" and out:
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(to_json(reports), encoding="utf-8", newline="\n")
    worst = max((r.max_severity() or Severity.INFO for r in reports), default=Severity.INFO)
    any_findings = any(r.findings for r in reports)
    if threshold is not None and any_findings and worst >= threshold:
        raise typer.Exit(1)
