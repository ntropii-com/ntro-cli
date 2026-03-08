"""ntro run — inspect workflow executions."""

from __future__ import annotations

from typing import Optional

import typer

from ntro.workspace.exceptions import NtroError
from ntro_cli import output as out
from ntro_cli.context import get_client

app = typer.Typer(help="Inspect workflow runs and execution history")


@app.command()
def status(id: str = typer.Argument(help="Task ID")) -> None:
    """Show the status of a workflow run."""
    try:
        client = get_client()
        task = client.tasks.get_sync(id)
        out.output(task, title=f"Run: {task.id}")
    except NtroError as e:
        out.print_error(str(e))
        raise typer.Exit(1)


@app.command("list")
def list_runs() -> None:
    """List scheduled / upcoming runs."""
    try:
        client = get_client()
        tasks = client.tasks.list_schedule_sync()
        out.output(
            tasks,
            columns=["id", "title", "workflowId", "status", "dueDate"],
            title="Schedule",
        )
    except NtroError as e:
        out.print_error(str(e))
        raise typer.Exit(1)


@app.command()
def history(
    tenant: str = typer.Option(..., "--tenant", help="Tenant ID", envvar="NTRO_TENANT"),
    entity: str = typer.Option(..., "--entity", help="Entity ID", envvar="NTRO_ENTITY"),
) -> None:
    """Show run history for a tenant/entity."""
    try:
        client = get_client()
        tasks = client.tasks.history_sync(tenant, entity)
        out.output(
            tasks,
            columns=["id", "title", "workflowId", "status", "createdAt"],
            title=f"History — {entity}",
        )
    except NtroError as e:
        out.print_error(str(e))
        raise typer.Exit(1)


@app.command()
def incoming() -> None:
    """List incoming (queued) runs."""
    try:
        client = get_client()
        items = client.tasks.list_incoming_sync()
        out.output(items, title="Incoming")
    except NtroError as e:
        out.print_error(str(e))
        raise typer.Exit(1)


@app.command()
def pending() -> None:
    """List pending (awaiting action) runs."""
    try:
        client = get_client()
        items = client.tasks.list_pending_sync()
        out.output(items, title="Pending")
    except NtroError as e:
        out.print_error(str(e))
        raise typer.Exit(1)
