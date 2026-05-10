"""ntro agent — manage external Group B agents (Claude MAs etc).

N-80: agents register external capabilities only (Claude MA, OpenAI
Assistant, Vertex Agent, Azure AI Agent). Runbooks are NOT agents —
``ntro workflow create`` deploys runbooks directly without going
through the agent registry.

Phase 2 (N-76) wires the registration ergonomics for `--path
anthropic://agents/<id>` etc; until then these subcommands cover
inspection + deletion of any agents created via the API directly.
"""

from __future__ import annotations

from typing import Optional

import typer

from ntro.workspace.exceptions import NtroError
from ntro_cli import output as out
from ntro_cli.context import get_client

app = typer.Typer(help="Inspect or delete agents (power user)")


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
            columns=["id", "tenantId", "name", "kind", "externalRef"],
            title="Agents",
        )
    except NtroError as e:
        out.print_error(str(e))
        raise typer.Exit(1)


@app.command()
def info(id: str = typer.Argument(help="Agent ID")) -> None:
    """Show agent details (with capability_manifest version snapshots)."""
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
    """Delete an external agent registration."""
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
