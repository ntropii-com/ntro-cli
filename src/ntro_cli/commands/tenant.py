"""ntro tenant — manage client cells."""

from __future__ import annotations

from typing import Optional

import typer

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

app = typer.Typer(help="Manage tenants (client cells)")
ai_app = typer.Typer(help="Configure tenant AI provider (model + provider)")
app.add_typer(ai_app, name="ai")


VALID_DATA_PLATFORMS = ("managed-postgres", "snowflake", "microsoft-fabric")


@app.command()
def create(
    name: Optional[str] = typer.Option(None, help="Tenant display name"),
    slug: Optional[str] = typer.Option(None, help="URL-safe identifier"),
    data_platform: Optional[str] = typer.Option(
        None,
        "--data-platform",
        help=(
            "Required. The data-platform strategy for this tenant. "
            f"One of: {', '.join(VALID_DATA_PLATFORMS)}. "
            "'managed-postgres' lets Ntropii provision the database; "
            "'snowflake' / 'microsoft-fabric' bind to a customer config "
            "(requires --data-platform-config)."
        ),
    ),
    data_platform_config: Optional[str] = typer.Option(
        None,
        "--data-platform-config",
        help=(
            "ID of a registered data platform config (required when "
            "--data-platform is not 'managed-postgres')."
        ),
    ),
    integration: Optional[str] = typer.Option(
        None,
        "--integration",
        help="DEPRECATED — use --data-platform-config instead.",
        hidden=True,
    ),
    json_input: Optional[str] = typer.Option(None, "--json", help="JSON payload (inline or @file)"),
) -> None:
    """Create a new tenant."""
    try:
        # Honour the deprecated alias for one release.
        if integration and not data_platform_config:
            out.print_warning(
                "--integration is deprecated; use --data-platform-config instead."
            )
            data_platform_config = integration

        if json_input:
            payload = load_json_input(json_input)
        else:
            if not name or not slug or not data_platform:
                raise typer.BadParameter(
                    "Provide --name, --slug, and --data-platform (or use --json)"
                )
            if data_platform not in VALID_DATA_PLATFORMS:
                raise typer.BadParameter(
                    f"--data-platform must be one of: {', '.join(VALID_DATA_PLATFORMS)} "
                    f"(got '{data_platform}')"
                )

            # Fail-fast: API enforces these too, but catching here saves a round-trip.
            is_managed = data_platform == "managed-postgres"
            if is_managed and data_platform_config:
                raise typer.BadParameter(
                    "--data-platform-config must not be set when --data-platform is "
                    "'managed-postgres' (Ntropii provisions the database)"
                )
            if not is_managed and not data_platform_config:
                raise typer.BadParameter(
                    f"--data-platform-config is required when --data-platform is '{data_platform}'"
                )

            payload = {
                "name": name,
                "slug": slug,
                "dataPlatform": data_platform,
            }
            if data_platform_config:
                payload["dataPlatformConfigId"] = data_platform_config

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


# ── ntro tenant ai ──────────────────────────────────────────────────
#
# Convenience over `tenant config set/get` for the most common config
# section. Persists under `tenants.config.ai` server-side; resolved at
# task dispatch with optional override on `entities.config.ai`.


@ai_app.command("show")
def ai_show(id: str = typer.Argument(help="Tenant slug or ID")) -> None:
    """Show the tenant's current AI provider configuration."""
    try:
        client = get_client()
        tenant = client.tenants.get_sync(id)
        cfg = parse_existing_config(getattr(tenant, "config", None))
        render_ai_section(cfg, title=f"Tenant {tenant.slug} — AI configuration")
    except NtroError as e:
        out.print_error(str(e))
        raise typer.Exit(1)


@ai_app.command("set")
def ai_set(
    id: str = typer.Argument(help="Tenant slug or ID"),
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
    """Set the tenant's AI provider configuration (replaces the .ai
    sub-section; other config keys untouched)."""
    if not any([provider, extraction_model, judgement_model, default_model]):
        raise typer.BadParameter(
            "Provide at least one of: --provider, --extraction-model, "
            "--judgement-model, --default-model"
        )
    try:
        client = get_client()
        tenant = client.tenants.get_sync(id)
        existing = parse_existing_config(getattr(tenant, "config", None))
        ai_section = build_ai_section(
            provider=provider,
            extraction_model=extraction_model,
            judgement_model=judgement_model,
            default_model=default_model,
        )
        merged = merge_ai_into_config(existing, ai_section)
        updated = client.tenants.update_sync(id, config=merged)
        cfg = parse_existing_config(getattr(updated, "config", None))
        render_ai_section(cfg, title=f"Tenant {updated.slug} — AI configuration")
    except NtroError as e:
        out.print_error(str(e))
        raise typer.Exit(1)


@ai_app.command("reset")
def ai_reset(id: str = typer.Argument(help="Tenant slug or ID")) -> None:
    """Clear the tenant's AI override; falls back to workspace default."""
    try:
        client = get_client()
        tenant = client.tenants.get_sync(id)
        existing = parse_existing_config(getattr(tenant, "config", None))
        merged = merge_ai_into_config(existing, {})
        updated = client.tenants.update_sync(id, config=merged)
        out.print_success(
            f"Tenant {updated.slug}: AI override cleared. "
            f"Falls back to workspace default (Anthropic Haiku)."
        )
    except NtroError as e:
        out.print_error(str(e))
        raise typer.Exit(1)
