"""ntro tenant — manage client cells."""

from __future__ import annotations

from typing import Optional

import typer

from ntro.workspace.exceptions import NtroError
from ntro_cli import output as out
from ntro_cli.context import get_client
from ntro_cli.helpers import load_json_input

app = typer.Typer(help="Manage tenants (client cells)")


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
