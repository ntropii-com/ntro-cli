"""ntro auth — connection management and identity."""

from __future__ import annotations

from typing import Optional

import typer

from ntro.workspace.config import load_config, save_config, write_default_config
from ntro.workspace.exceptions import NtroError
from ntro_cli import output as out
from ntro_cli.context import get_client

app = typer.Typer(help="Manage connections and verify identity")


@app.command()
def login(
    name: str = typer.Option("local", "--name", "-n", help="Connection name"),
    host: str = typer.Option("http://localhost:3000/v1", "--host", help="API host URL"),
    api_key: Optional[str] = typer.Option(None, "--api-key", help="API key"),
    default_tenant: Optional[str] = typer.Option(None, "--tenant", help="Default tenant slug"),
    set_default: bool = typer.Option(True, "--set-default/--no-set-default", help="Set as default connection"),
    no_interactive: bool = typer.Option(False, "--no-interactive", help="Skip prompts (use flags only)"),
) -> None:
    """Add or update a connection in ~/.ntro/config.toml."""
    write_default_config()
    config = load_config()

    if not no_interactive:
        name = typer.prompt("Connection name", default=name)
        host = typer.prompt("API host", default=host)
        api_key = typer.prompt("API key", default=api_key or "", hide_input=True) or None
        default_tenant = typer.prompt("Default tenant (optional)", default=default_tenant or "", show_default=False) or None

    from ntro.workspace.config import ConnectionConfig
    config.connections[name] = ConnectionConfig(
        name=name,
        host=host,
        api_key=api_key or "",
        default_tenant=default_tenant,
    )

    if set_default:
        config.default_connection_name = name

    save_config(config)
    out.print_success(f"Connection '{name}' saved → {host}")
    if set_default:
        out.print_success(f"Default connection set to '{name}'")


@app.command("list")
def list_connections() -> None:
    """List all configured connections."""
    config = load_config()
    if not config.connections:
        out.print_warning("No connections configured. Run 'ntro auth login' to add one.")
        return

    rows = []
    for name, conn in config.connections.items():
        rows.append({
            "name": name,
            "host": conn.host,
            "default_tenant": conn.default_tenant or "",
            "active": "●" if name == config.default_connection_name else "",
        })
    out.output(rows, columns=["active", "name", "host", "default_tenant"], title="Connections")


@app.command()
def test(
    connection: Optional[str] = typer.Option(None, "-c", "--connection", help="Connection to test"),
) -> None:
    """Test a connection by calling GET /me."""
    try:
        client = get_client()
        profile = client.identity.whoami_sync()
        out.print_success(f"Connected as {profile.email} (org: {profile.orgId})")
    except NtroError as e:
        out.print_error(str(e))
        raise typer.Exit(1)


@app.command("set-default")
def set_default(name: str = typer.Argument(help="Connection name to set as default")) -> None:
    """Set the default connection."""
    config = load_config()
    if name not in config.connections:
        out.print_error(f"Connection '{name}' not found. Available: {list(config.connections.keys())}")
        raise typer.Exit(1)
    config.default_connection_name = name
    save_config(config)
    out.print_success(f"Default connection set to '{name}'")


@app.command()
def whoami() -> None:
    """Show current user identity (calls GET /me)."""
    try:
        client = get_client()
        profile = client.identity.whoami_sync()
        out.output(profile, title="Current User")
    except NtroError as e:
        out.print_error(str(e))
        raise typer.Exit(1)
