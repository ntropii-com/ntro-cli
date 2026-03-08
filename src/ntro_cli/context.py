"""CLI context — SDK client initialisation and shared state."""

from __future__ import annotations

import click

from ntro.workspace import Client


def get_client() -> Client:
    """Build and return a Client from the current Typer context."""
    ctx = click.get_current_context()
    obj: dict = ctx.ensure_object(dict)

    if "client" not in obj:
        connection: str | None = obj.get("connection")
        host: str | None = obj.get("host")
        debug: bool = obj.get("debug", False)

        if host:
            # Explicit host overrides config entirely
            from ntro.workspace.config import load_config
            conn_name = connection or None
            try:
                cfg = load_config().get_connection(conn_name)
                api_key = cfg.api_key
            except Exception:
                api_key = ""
            obj["client"] = Client(host=host, api_key=api_key, debug=debug)
        else:
            obj["client"] = Client.from_config(connection=connection, debug=debug)

    return obj["client"]
