"""ntro entity — manage SPVs/funds within a tenant."""

from __future__ import annotations

import os
from typing import Optional

import click
import typer

from ntro.workspace.config import load_config
from ntro.workspace.exceptions import NtroError
from ntro_cli import output as out
from ntro_cli.commands._ai_helpers import (
    build_ai_section,
    merge_ai_into_config,
    parse_existing_config,
    render_ai_section,
)
from ntro_cli.context import get_client
from ntro_cli.helpers import load_json_input

app = typer.Typer(help="Manage entities (SPVs/funds within a tenant)")
ai_app = typer.Typer(help="Configure entity-level AI provider override")
app.add_typer(ai_app, name="ai")


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


# ── ntro entity ai ──────────────────────────────────────────────────
#
# Entity-level AI provider override. Inherits from tenant.config.ai
# unless explicitly set here.


def _find_entity(client, tenant_id: str, entity_id: str):
    """List entities for the tenant and pick the one matching id-or-slug.
    Avoids needing a dedicated GET /entities/:id endpoint for the PoC."""
    entities = client.entities.list_sync(tenant_id=tenant_id)
    for ent in entities:
        if ent.id == entity_id or ent.slug == entity_id:
            return ent
    raise typer.BadParameter(
        f"Entity '{entity_id}' not found in tenant '{tenant_id}'."
    )


@ai_app.command("show")
def ai_show(
    entity_id: str = typer.Argument(help="Entity slug or ID"),
    tenant: Optional[str] = typer.Option(
        None, "--tenant", help="Tenant slug or ID", envvar="NTRO_TENANT"
    ),
) -> None:
    """Show this entity's AI override (or note that it inherits from the tenant)."""
    try:
        tenant_id = _resolve_tenant(tenant)
        client = get_client()
        entity = _find_entity(client, tenant_id, entity_id)
        cfg = parse_existing_config(getattr(entity, "config", None))
        render_ai_section(cfg, title=f"Entity {entity.slug} — AI configuration")
    except NtroError as e:
        out.print_error(str(e))
        raise typer.Exit(1)


@ai_app.command("set")
def ai_set(
    entity_id: str = typer.Argument(help="Entity slug or ID"),
    tenant: Optional[str] = typer.Option(
        None, "--tenant", help="Tenant slug or ID", envvar="NTRO_TENANT"
    ),
    provider: Optional[str] = typer.Option(
        None,
        "--provider",
        help="One of: NTROPII, ANTHROPIC, AZURE_OPENAI, BEDROCK, DATABRICKS_FM",
    ),
    extraction_model: Optional[str] = typer.Option(
        None, "--extraction-model", help="Model for ai.extract() calls"
    ),
    judgement_model: Optional[str] = typer.Option(
        None, "--judgement-model", help="Model for run_quality_check() calls"
    ),
    default_model: Optional[str] = typer.Option(
        None, "--default-model", help="Fallback model when capability slot is unset"
    ),
) -> None:
    """Set the entity's AI provider override (replaces the .ai sub-section)."""
    if not any([provider, extraction_model, judgement_model, default_model]):
        raise typer.BadParameter(
            "Provide at least one of: --provider, --extraction-model, "
            "--judgement-model, --default-model"
        )
    try:
        tenant_id = _resolve_tenant(tenant)
        client = get_client()
        entity = _find_entity(client, tenant_id, entity_id)
        existing = parse_existing_config(getattr(entity, "config", None))
        ai_section = build_ai_section(
            provider=provider,
            extraction_model=extraction_model,
            judgement_model=judgement_model,
            default_model=default_model,
        )
        merged = merge_ai_into_config(existing, ai_section)
        updated = client.entities.update_sync(tenant_id, entity_id, config=merged)
        cfg = parse_existing_config(getattr(updated, "config", None))
        render_ai_section(cfg, title=f"Entity {updated.slug} — AI configuration")
    except NtroError as e:
        out.print_error(str(e))
        raise typer.Exit(1)


@ai_app.command("reset")
def ai_reset(
    entity_id: str = typer.Argument(help="Entity slug or ID"),
    tenant: Optional[str] = typer.Option(
        None, "--tenant", help="Tenant slug or ID", envvar="NTRO_TENANT"
    ),
) -> None:
    """Clear the entity's AI override; inherits from tenant.config.ai."""
    try:
        tenant_id = _resolve_tenant(tenant)
        client = get_client()
        entity = _find_entity(client, tenant_id, entity_id)
        existing = parse_existing_config(getattr(entity, "config", None))
        merged = merge_ai_into_config(existing, {})
        updated = client.entities.update_sync(tenant_id, entity_id, config=merged)
        out.print_success(
            f"Entity {updated.slug}: AI override cleared. Inherits from tenant."
        )
    except NtroError as e:
        out.print_error(str(e))
        raise typer.Exit(1)
