"""ntro workflow — definition, deployment, and triggering."""

from __future__ import annotations

import time
from pathlib import Path
from typing import Optional

import typer

from ntro.workspace.exceptions import NtroError
from ntro.workspace.models.common import TaskStatus
from ntro_cli import output as out
from ntro_cli.context import get_client
from ntro_cli.helpers import load_json_input

app = typer.Typer(help="Manage workflow definitions, deployments, and runs")


@app.command()
def create(
    name: Optional[str] = typer.Option(None, help="Workflow name (slug)"),
    description: Optional[str] = typer.Option(None, help="Description"),
    tenant: Optional[str] = typer.Option(None, "--tenant", help="Tenant ID"),
    schedule: Optional[str] = typer.Option(None, help="Cron schedule (e.g. '0 8 5 * *')"),
    timezone: Optional[str] = typer.Option(None, help="Timezone (e.g. Europe/London)"),
    json_input: Optional[str] = typer.Option(None, "--json", help="JSON payload (inline or @file)"),
) -> None:
    """Register a new workflow definition."""
    try:
        if json_input:
            payload = load_json_input(json_input)
        else:
            if not name:
                raise typer.BadParameter("Provide --name (or use --json)")
            payload = {
                "name": name,
                "description": description,
                "tenantId": tenant,
                "schedule": schedule,
                "timezone": timezone,
            }

        client = get_client()
        wf = client.workflows.create_sync(**payload)
        out.output(wf, title=f"Workflow created: {wf.name}")
    except NtroError as e:
        out.print_error(str(e))
        raise typer.Exit(1)


@app.command("list")
def list_workflows() -> None:
    """List all registered workflows."""
    try:
        client = get_client()
        workflows = client.workflows.list_sync()
        out.output(
            workflows,
            columns=["id", "name", "description", "schedule", "latestVersion"],
            title="Workflows",
        )
    except NtroError as e:
        out.print_error(str(e))
        raise typer.Exit(1)


@app.command()
def info(id: str = typer.Argument(help="Workflow ID or name")) -> None:
    """Show workflow details."""
    try:
        client = get_client()
        wf = client.workflows.get_sync(id)
        out.output(wf, title=f"Workflow: {wf.name}")
    except NtroError as e:
        out.print_error(str(e))
        raise typer.Exit(1)


@app.command()
def push(
    id: str = typer.Argument(help="Workflow ID"),
    file: Path = typer.Argument(help="Artifact file to upload (.zip or .tar.gz)"),
) -> None:
    """Upload a new workflow version artifact."""
    try:
        if not file.exists():
            out.print_error(f"File not found: {file}")
            raise typer.Exit(1)

        client = get_client()
        version = client.workflows.push_sync(id, file)
        out.output(version, title=f"Version pushed: {version.version}")
    except NtroError as e:
        out.print_error(str(e))
        raise typer.Exit(1)


@app.command()
def deploy(
    workflow_id: Optional[str] = typer.Option(None, "--workflow", help="Workflow ID"),
    version_id: Optional[str] = typer.Option(None, "--version", help="Workflow version ID"),
    tenant: Optional[str] = typer.Option(None, "--tenant", help="Tenant ID"),
    entity: Optional[str] = typer.Option(None, "--entity", help="Entity ID"),
    json_input: Optional[str] = typer.Option(None, "--json", help="JSON payload (inline or @file)"),
) -> None:
    """Deploy a workflow version to a tenant/entity."""
    try:
        if json_input:
            payload = load_json_input(json_input)
        else:
            if not workflow_id or not version_id:
                raise typer.BadParameter("Provide --workflow and --version (or use --json)")
            payload = {
                "workflowId": workflow_id,
                "workflowVersionId": version_id,
                "tenantId": tenant,
                "entityId": entity,
            }

        client = get_client()
        deployment = client.deployments.create_sync(**payload)
        out.output(deployment, title=f"Deployment created: {deployment.id}")
    except NtroError as e:
        out.print_error(str(e))
        raise typer.Exit(1)


@app.command("deploy-status")
def deploy_status(id: str = typer.Argument(help="Deployment ID")) -> None:
    """Check deployment status."""
    try:
        client = get_client()
        deployment = client.deployments.get_sync(id)
        out.output(deployment, title=f"Deployment: {deployment.id}")
    except NtroError as e:
        out.print_error(str(e))
        raise typer.Exit(1)


@app.command("run")
def run_workflow(
    name: str = typer.Argument(help="Workflow name (e.g. nav-monthly)"),
    tenant: Optional[str] = typer.Option(None, "--tenant", help="Tenant ID", envvar="NTRO_TENANT"),
    entity: Optional[str] = typer.Option(None, "--entity", help="Entity ID", envvar="NTRO_ENTITY"),
    period: Optional[str] = typer.Option(None, "--period", help="Accounting period (e.g. 2026-03)"),
    priority: Optional[str] = typer.Option(None, "--priority", help="Priority: LOW, NORMAL, HIGH"),
    dry_run: bool = typer.Option(False, "--dry-run", help="Validate without committing"),
    wait: bool = typer.Option(False, "--wait", help="Poll until task completes"),
    json_input: Optional[str] = typer.Option(None, "--json", help="JSON payload (inline or @file)"),
) -> None:
    """Trigger a workflow run."""
    try:
        if json_input:
            payload = load_json_input(json_input)
        else:
            if not tenant:
                raise typer.BadParameter("Provide --tenant or set NTRO_TENANT / default_tenant in config")
            context: dict = {}
            if period:
                context["period"] = period
            if priority:
                context["priority"] = priority
            if dry_run:
                context["dry_run"] = True
            payload = {
                "tenantId": tenant,
                "entityId": entity,
                "workflowId": name,
                "context": context,
            }

        client = get_client()
        task = client.tasks.create_sync(**payload)
        out.output(task, title=f"Run started: {task.id}")

        if wait:
            _poll_task(client, task.id)

    except NtroError as e:
        out.print_error(str(e))
        raise typer.Exit(1)


def _poll_task(client, task_id: str, interval: int = 3, timeout: int = 300) -> None:
    from rich.console import Console
    console = Console()
    deadline = time.monotonic() + timeout

    with console.status(f"Waiting for task {task_id}...") as status:
        while time.monotonic() < deadline:
            try:
                task = client.tasks.get_sync(task_id)
                status.update(f"[dim]{task.status}[/dim] — {task.id}")
                if task.status in (TaskStatus.COMPLETED, TaskStatus.FAILED, TaskStatus.CANCELLED):
                    break
                time.sleep(interval)
            except NtroError:
                time.sleep(interval)

    try:
        task = client.tasks.get_sync(task_id)
        out.output(task, title=f"Final status: {task.status}")
    except NtroError as e:
        out.print_error(str(e))
