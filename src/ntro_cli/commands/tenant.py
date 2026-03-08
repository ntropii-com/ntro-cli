"""ntro tenant — manage client cells."""

from __future__ import annotations

from typing import Optional

import typer

from ntro.workspace.exceptions import NtroError
from ntro_cli import output as out
from ntro_cli.context import get_client
from ntro_cli.helpers import load_json_input

app = typer.Typer(help="Manage tenants (client cells)")


@app.command()
def create(
    name: Optional[str] = typer.Option(None, help="Tenant display name"),
    slug: Optional[str] = typer.Option(None, help="URL-safe identifier"),
    integration: Optional[str] = typer.Option(None, "--integration", help="Data platform config ID"),
    json_input: Optional[str] = typer.Option(None, "--json", help="JSON payload (inline or @file)"),
) -> None:
    """Create a new tenant."""
    try:
        if json_input:
            payload = load_json_input(json_input)
        else:
            if not name or not slug:
                raise typer.BadParameter("Provide --name and --slug (or use --json)")
            payload = {"name": name, "slug": slug, "dataPlatformConfigId": integration}

        client = get_client()
        tenant = client.tenants.create_sync(**payload)
        out.output(tenant, title=f"Tenant created: {tenant.slug}")
    except NtroError as e:
        out.print_error(str(e))
        raise typer.Exit(1)


@app.command("list")
def list_tenants() -> None:
    """List all tenants."""
    try:
        client = get_client()
        tenants = client.tenants.list_sync()
        out.output(tenants, columns=["id", "slug", "name", "status", "entityCount"], title="Tenants")
    except NtroError as e:
        out.print_error(str(e))
        raise typer.Exit(1)


@app.command()
def info(id: str = typer.Argument(help="Tenant slug or ID")) -> None:
    """Show tenant details."""
    try:
        client = get_client()
        tenant = client.tenants.get_sync(id)
        out.output(tenant, title=f"Tenant: {tenant.slug}")
    except NtroError as e:
        out.print_error(str(e))
        raise typer.Exit(1)
