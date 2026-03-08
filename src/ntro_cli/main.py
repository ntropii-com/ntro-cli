"""ntro CLI — root Typer app."""

from __future__ import annotations

import logging
from typing import Optional

import typer

from ntro_cli import output as out
from ntro_cli.commands import auth, entity, integration, run, tenant, workflow

app = typer.Typer(
    name="ntro",
    help="ntro platform CLI",
    no_args_is_help=True,
    pretty_exceptions_show_locals=False,
)

app.add_typer(auth.app, name="auth")
app.add_typer(integration.app, name="integration")
app.add_typer(tenant.app, name="tenant")
app.add_typer(entity.app, name="entity")
app.add_typer(workflow.app, name="workflow")
app.add_typer(run.app, name="run")


@app.callback()
def main(
    ctx: typer.Context,
    connection: Optional[str] = typer.Option(
        None, "-c", "--connection",
        help="Connection name from ~/.ntro/config.toml",
        envvar="NTRO_DEFAULT_CONNECTION_NAME",
    ),
    host: Optional[str] = typer.Option(
        None, "--host",
        help="Override API host URL (e.g. http://localhost:3000/v1)",
        envvar="NTRO_HOST",
    ),
    output: str = typer.Option(
        "text", "-o", "--output",
        help="Output format: text or json",
    ),
    debug: bool = typer.Option(False, "--debug", help="Enable debug logging"),
    log_level: Optional[str] = typer.Option(
        None, "--log-level",
        help="Log level: DEBUG, INFO, WARN, ERROR",
    ),
) -> None:
    """ntro platform CLI.

    Default API: https://api.ntropii.com/v1
    Local dev:   http://localhost:3000/v1  (use -c local or --host)

    Quickstart:
      ntro auth login          # configure a connection
      ntro auth whoami         # verify identity
      ntro tenant list         # list tenants
    """
    ctx.ensure_object(dict)
    ctx.obj["connection"] = connection
    ctx.obj["host"] = host
    ctx.obj["debug"] = debug

    out.set_format(output)

    if debug or log_level:
        level = getattr(logging, (log_level or "DEBUG").upper(), logging.DEBUG)
        logging.basicConfig(level=level, format="%(name)s %(levelname)s %(message)s")
