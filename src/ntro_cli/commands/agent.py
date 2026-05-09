"""ntro agent — power-user agent management.

Most users won't need this — `ntro workflow push --path` upserts the agent
implicitly. These subcommands are for inspection, deletion, and forcing a
capability-manifest refresh on external-kind agents (Phase 2+).
"""

from __future__ import annotations

from typing import Optional

import typer

from ntro.workspace.exceptions import NtroError
from ntro_cli import output as out
from ntro_cli.context import get_client

app = typer.Typer(help="Inspect, refresh, or delete agents (power user)")


@app.command("list")
def list_agents(
    tenant: Optional[str] = typer.Option(None, "--tenant", help="Filter by tenant slug or id"),
) -> None:
    """List agents across the workspace, or under a single tenant."""
    try:
        client = get_client()
        tenant_id: Optional[str] = None
        if tenant:
            for t in client.tenants.list_sync():
                if t.id == tenant or t.slug == tenant:
                    tenant_id = t.id
                    break
            if tenant_id is None:
                raise typer.BadParameter(f"No tenant matches '{tenant}'.")
        agents = client.agents.list_sync(tenant_id=tenant_id)
        out.output(
            agents,
            columns=["id", "tenantId", "name", "kind", "packageName", "externalRef"],
            title="Agents",
        )
    except NtroError as e:
        out.print_error(str(e))
        raise typer.Exit(1)


@app.command()
def info(id: str = typer.Argument(help="Agent ID")) -> None:
    """Show agent details (with versions for kind=runbook)."""
    try:
        client = get_client()
        agent = client.agents.get_sync(id)
        out.output(agent, title=f"Agent: {agent.name}")
    except NtroError as e:
        out.print_error(str(e))
        raise typer.Exit(1)


@app.command()
def delete(
    id: str = typer.Argument(help="Agent ID"),
    yes: bool = typer.Option(False, "--yes", "-y", help="Skip confirmation"),
) -> None:
    """Delete an agent. Fails if any workflows reference it."""
    try:
        client = get_client()
        if not yes:
            agent = client.agents.get_sync(id)
            confirm = typer.confirm(
                f"Delete agent '{agent.name}' (kind={agent.kind})?",
                default=False,
            )
            if not confirm:
                out.print_warning("Cancelled.")
                raise typer.Exit(0)
        client.agents.delete_sync(id)
        out.print_success(f"Agent {id} deleted.")
    except NtroError as e:
        out.print_error(str(e))
        raise typer.Exit(1)


@app.command()
def refresh(id: str = typer.Argument(help="Agent ID")) -> None:
    """Force refresh of capability_manifest from the ecosystem.

    No-op for kind=runbook in Phase 1; throws Phase-2 marker for external
    kinds. Endpoint shape stable from day one.
    """
    try:
        client = get_client()
        agent = client.agents.refresh_sync(id)
        out.output(agent, title=f"Agent refreshed: {agent.name}")
    except NtroError as e:
        out.print_error(str(e))
        raise typer.Exit(1)
