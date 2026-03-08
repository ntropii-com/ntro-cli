"""ntro entity — manage SPVs/funds within a tenant."""

from __future__ import annotations

import os
from typing import Optional

import click
import typer

from ntro.workspace.config import load_config
from ntro.workspace.exceptions import NtroError
from ntro_cli import output as out
from ntro_cli.context import get_client
from ntro_cli.helpers import load_json_input

app = typer.Typer(help="Manage entities (SPVs/funds within a tenant)")


def _resolve_tenant(tenant_flag: Optional[str]) -> str:
    """Resolve tenant from flag > env var > config default."""
    if tenant_flag:
        return tenant_flag
    env = os.environ.get("NTRO_TENANT")
    if env:
        return env
    try:
        ctx = click.get_current_context()
        conn_name = ctx.obj.get("connection") if ctx.obj else None
        config = load_config()
        conn = config.get_connection(conn_name)
        if conn.default_tenant:
            return conn.default_tenant
    except Exception:
        pass
    raise typer.BadParameter(
        "Tenant required. Use --tenant, set NTRO_TENANT, or set default_tenant in config."
    )


@app.command()
def create(
    name: Optional[str] = typer.Option(None, help="Entity display name"),
    slug: Optional[str] = typer.Option(None, help="URL-safe identifier"),
    tenant: Optional[str] = typer.Option(None, "--tenant", help="Tenant slug or ID", envvar="NTRO_TENANT"),
    entity_type: Optional[str] = typer.Option(None, "--type", help="Entity type (e.g. real-estate-spv)"),
    jurisdiction: Optional[str] = typer.Option(None, help="Legal jurisdiction"),
    currency: Optional[str] = typer.Option(None, help="Base currency (e.g. GBP)"),
    schema: Optional[str] = typer.Option(None, help="Databricks schema name"),
    json_input: Optional[str] = typer.Option(None, "--json", help="JSON payload (inline or @file)"),
) -> None:
    """Create a new entity within a tenant."""
    try:
        tenant_id = _resolve_tenant(tenant)

        if json_input:
            payload = load_json_input(json_input)
        else:
            if not name or not slug:
                raise typer.BadParameter("Provide --name and --slug (or use --json)")
            payload = {
                "name": name,
                "slug": slug,
                "type": entity_type,
                "jurisdiction": jurisdiction,
                "currency": currency,
                "schema": schema,
            }

        client = get_client()
        entity = client.entities.create_sync(tenant_id=tenant_id, **payload)
        out.output(entity, title=f"Entity created: {entity.slug}")
    except NtroError as e:
        out.print_error(str(e))
        raise typer.Exit(1)


@app.command("list")
def list_entities(
    tenant: Optional[str] = typer.Option(None, "--tenant", help="Filter by tenant", envvar="NTRO_TENANT"),
) -> None:
    """List entities (optionally filtered by tenant)."""
    try:
        client = get_client()
        entities = client.entities.list_sync(tenant_id=tenant)
        out.output(
            entities,
            columns=["id", "slug", "name", "tenantId", "type", "currency"],
            title="Entities",
        )
    except NtroError as e:
        out.print_error(str(e))
        raise typer.Exit(1)
