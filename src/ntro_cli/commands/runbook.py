"""ntro runbook — author-side commands operating on a runbook directory.

For v1 this group hosts a single command, ``ntro runbook validate
<path>``, which runs the SDK validator against a local runbook
directory and prints a human-readable report. The same primitive runs
inside the canonical worker via the ``ntro_ops.validate_runbook``
activity (N-93) — running it locally first catches obvious shape
issues without a deploy cycle.

Exit codes
----------

The command follows a tri-state convention so CI pipelines can branch:

- ``0`` — runbook is valid (``report.ok is True``)
- ``1`` — runbook has validation errors (file shape, frontmatter, imports)
- ``2`` — infrastructure failure (path does not exist, not a directory)
"""

from __future__ import annotations

from pathlib import Path

import typer
from rich.console import Console

from ntro.runbook import validate_runbook

app = typer.Typer(help="Local checks against a runbook directory")

console = Console()
err_console = Console(stderr=True)


@app.command("validate")
def validate(
    path: Path = typer.Argument(
        ...,
        help="Path to a runbook directory (contains runbook.md and templates/)",
        exists=False,  # we handle missing-path ourselves to emit exit code 2
        file_okay=False,
        dir_okay=True,
        resolve_path=True,
    ),
) -> None:
    """Validate a local runbook directory.

    Runs the same checks the worker runs on deploy:

    \b
    - runbook.md exists with parseable YAML frontmatter
    - required frontmatter fields (slug, name, version, state, author)
    - templates/workflow.py imports + has the <Slug>Workflow class
    - templates/activities.py exists and imports
    - templates/models.py imports (if present)
    """
    # Tri-state exit: 2 for "the path itself is wrong" (infra), so
    # CI can distinguish "you fat-fingered the path" from "the runbook
    # is genuinely broken". The validator emits RUNBOOK_DIR_NOT_FOUND
    # as a regular error, but the CLI re-classifies it here.
    if not path.exists():
        err_console.print(f"[red]Path does not exist:[/red] {path}")
        raise typer.Exit(code=2)
    if not path.is_dir():
        err_console.print(f"[red]Path is not a directory:[/red] {path}")
        raise typer.Exit(code=2)

    report = validate_runbook(path)
    _print_report(report, path)

    if not report.ok:
        raise typer.Exit(code=1)


def _print_report(report, runbook_dir: Path) -> None:
    """Render a ValidationReport as a human-readable summary.

    Layout: one line per check status block, then a summary line. Uses
    Rich for colour but keeps the format scannable even when colour is
    stripped (CI logs). The ``✓``/``✗`` glyphs work in every terminal
    we ship to today; if we need ASCII-only we can swap to ``[ok]`` /
    ``[err]`` later.
    """
    console.print(f"[bold]Validating runbook:[/bold] {runbook_dir}")

    if report.ok and not report.warnings:
        console.print("[green]✓ all checks passed[/green]")
        console.print()
        console.print("[bold green]OK[/bold green] — 0 errors, 0 warnings")
        return

    if report.errors:
        console.print()
        console.print("[bold red]Errors:[/bold red]")
        for issue in report.errors:
            loc = f" ({issue.path})" if issue.path else ""
            console.print(f"  [red]✗[/red] [{issue.code}]{loc} {issue.message}")

    if report.warnings:
        console.print()
        console.print("[bold yellow]Warnings:[/bold yellow]")
        for issue in report.warnings:
            loc = f" ({issue.path})" if issue.path else ""
            console.print(f"  [yellow]![/yellow] [{issue.code}]{loc} {issue.message}")

    console.print()
    status_label = "[bold green]OK[/bold green]" if report.ok else "[bold red]FAIL[/bold red]"
    console.print(
        f"{status_label} — {len(report.errors)} errors, {len(report.warnings)} warnings"
    )
