"""ntro integration — data platforms and email sources."""

from __future__ import annotations

from typing import Optional

import typer

from ntro.workspace.exceptions import NtroError
from ntro_cli import output as out
from ntro_cli.context import get_client
from ntro_cli.helpers import load_json_input

app = typer.Typer(help="Manage data platform integrations and email sources")
add_app = typer.Typer(help="Add a new integration")
app.add_typer(add_app, name="add")


@add_app.command()
def databricks(
    name: Optional[str] = typer.Option(None, help="Display name"),
    workspace_url: Optional[str] = typer.Option(None, "--workspace-url", help="Databricks workspace URL"),
    catalog: Optional[str] = typer.Option(None, help="Unity Catalog name"),
    client_id: Optional[str] = typer.Option(None, "--client-id", help="Service principal client ID"),
    client_secret: Optional[str] = typer.Option(None, "--client-secret", help="Service principal secret", hide_input=True),
    region: Optional[str] = typer.Option(None, help="Azure region (e.g. UK-South)"),
    json_input: Optional[str] = typer.Option(None, "--json", help="JSON payload (inline or @file)"),
) -> None:
    """Register a Databricks data platform."""
    try:
        if json_input:
            payload = load_json_input(json_input)
        else:
            if not all([name, workspace_url, catalog]):
                raise typer.BadParameter("Provide --name, --workspace-url, --catalog (or use --json)")
            payload = {
                "name": name,
                "provider": "DATABRICKS",
                "region": region,
                "config": {
                    "workspaceUrl": workspace_url,
                    "catalog": catalog,
                    "authType": "service-principal",
                    "clientId": client_id,
                    "clientSecret": client_secret,
                },
            }

        client = get_client()
        result = client.integrations.create_data_platform_sync(**payload)
        out.output(result, title=f"Integration created: {result.name}")
    except NtroError as e:
        out.print_error(str(e))
        raise typer.Exit(1)


@add_app.command()
def email(
    tenant_id: str = typer.Option(..., "--tenant", help="Tenant ID or slug"),
    provider: str = typer.Option("microsoft-graph", help="Email provider"),
    address: Optional[str] = typer.Option(None, help="Email address"),
    json_input: Optional[str] = typer.Option(None, "--json", help="JSON payload (inline or @file)"),
) -> None:
    """Add an email integration."""
    try:
        if json_input:
            payload = load_json_input(json_input)
        else:
            payload = {"tenantId": tenant_id, "provider": provider, "address": address}

        client = get_client()
        result = client.integrations.create_email_sync(**payload)
        out.output(result, title="Email integration created")
    except NtroError as e:
        out.print_error(str(e))
        raise typer.Exit(1)


@app.command("list")
def list_integrations() -> None:
    """List all data platform configs."""
    try:
        client = get_client()
        items = client.integrations.list_data_platforms_sync()
        out.output(items, columns=["id", "name", "provider", "region", "ownership"], title="Data Platforms")
    except NtroError as e:
        out.print_error(str(e))
        raise typer.Exit(1)


@app.command()
def info(id: str = typer.Argument(help="Data platform config ID")) -> None:
    """Show data platform details."""
    try:
        client = get_client()
        result = client.integrations.get_data_platform_sync(id)
        out.output(result, title=f"Integration: {result.name}")
    except NtroError as e:
        out.print_error(str(e))
        raise typer.Exit(1)


@app.command()
def test(id: str = typer.Argument(help="Data platform config ID")) -> None:
    """Test a data platform connection."""
    try:
        from rich.console import Console
        console = Console()
        client = get_client()
        with console.status("Testing connection..."):
            result = client.integrations.test_connection_sync(id)
        if result.success:
            out.print_success(f"{result.message}" + (f" ({result.latencyMs}ms)" if result.latencyMs else ""))
        else:
            out.print_error(result.message)
            raise typer.Exit(1)
    except NtroError as e:
        out.print_error(str(e))
        raise typer.Exit(1)


@app.command()
def discover(id: str = typer.Argument(help="Data platform config ID")) -> None:
    """Discover schemas in a data platform."""
    try:
        client = get_client()
        schemas = client.integrations.discover_schemas_sync(id)
        out.output(schemas, columns=["name"], title=f"Schemas in {id}")
    except NtroError as e:
        out.print_error(str(e))
        raise typer.Exit(1)
