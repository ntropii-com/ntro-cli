"""Output formatters — Rich tables/panels for text mode, raw JSON for json mode."""

from __future__ import annotations

import json
from typing import Any

from pydantic import BaseModel
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

console = Console()
err_console = Console(stderr=True)

# Current output format — set by main.py callback from --output flag
_output_format: str = "text"


def set_format(fmt: str) -> None:
    global _output_format
    _output_format = fmt


def get_format() -> str:
    return _output_format


def _to_dict(obj: Any) -> dict:
    if isinstance(obj, BaseModel):
        return obj.model_dump(mode="json")
    if isinstance(obj, dict):
        return obj
    return {"value": str(obj)}


def _to_dict_list(items: list) -> list[dict]:
    return [_to_dict(i) for i in items]


def output(
    data: Any,
    *,
    columns: list[str] | None = None,
    title: str | None = None,
) -> None:
    """Print data to stdout in the current output format."""
    if _output_format == "json":
        _print_json(data)
    else:
        if isinstance(data, list):
            _print_table(data, columns=columns, title=title)
        else:
            _print_panel(data, title=title)


def _print_json(data: Any) -> None:
    if isinstance(data, list):
        raw = [_to_dict(d) for d in data]
    elif isinstance(data, BaseModel):
        raw = data.model_dump()
    else:
        raw = data
    console.print_json(json.dumps(raw, default=str))


def _print_table(items: list, columns: list[str] | None, title: str | None) -> None:
    if not items:
        console.print("[dim]No results.[/dim]")
        return

    rows = _to_dict_list(items)

    # Determine columns: explicit list, or all keys from first row
    cols = columns or list(rows[0].keys())

    table = Table(title=title, show_header=True, header_style="bold cyan")
    for col in cols:
        table.add_column(col)

    for row in rows:
        table.add_row(*[str(row.get(col, "")) for col in cols])

    console.print(table)


def _print_panel(data: Any, title: str | None) -> None:
    row = _to_dict(data)
    lines = "\n".join(
        f"[bold]{k}[/bold]: {v}" for k, v in row.items() if v not in (None, "", [])
    )
    console.print(Panel(lines, title=title or "", expand=False))


def print_success(message: str) -> None:
    console.print(f"[green]✓[/green] {message}")


def print_error(message: str) -> None:
    err_console.print(f"[red]✗[/red] {message}")


def print_warning(message: str) -> None:
    console.print(f"[yellow]![/yellow] {message}")
