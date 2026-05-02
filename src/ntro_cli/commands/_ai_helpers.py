"""Shared helpers for `ntro tenant ai` and `ntro entity ai`.

The two command groups have identical UX (show / set / reset) but
target different resources. Putting the helpers here keeps the
command modules thin and avoids duplicating the validation /
formatting logic.
"""

from __future__ import annotations

import json
from typing import Any

import typer

from ntro_cli import output as out


VALID_PROVIDERS = ("NTROPII", "ANTHROPIC", "AZURE_OPENAI", "BEDROCK", "DATABRICKS_FM")


def parse_existing_config(value: Any) -> dict[str, Any]:
    """Server returns ``config`` as either a dict (typed) or a JSON
    string (older envelopes). Normalise to a dict."""
    if value is None or value == "":
        return {}
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError:
            return {}
        return parsed if isinstance(parsed, dict) else {}
    return {}


def build_ai_section(
    *,
    provider: str | None,
    extraction_model: str | None,
    judgement_model: str | None,
    default_model: str | None,
) -> dict[str, Any]:
    """Construct an `ai` sub-section dict from CLI flags. Empty fields
    are omitted so a partial set/replace is faithful."""
    if provider and provider not in VALID_PROVIDERS:
        raise typer.BadParameter(
            f"--provider must be one of: {', '.join(VALID_PROVIDERS)} (got '{provider}')"
        )
    ai: dict[str, Any] = {}
    if provider:
        ai["provider"] = provider
    models: dict[str, str] = {}
    if extraction_model:
        models["extraction"] = extraction_model
    if judgement_model:
        models["judgement"] = judgement_model
    if default_model:
        models["default"] = default_model
    if models:
        ai["models"] = models
    return ai


def merge_ai_into_config(
    existing_config: dict[str, Any], ai_section: dict[str, Any]
) -> dict[str, Any]:
    """Replace the `.ai` sub-section while leaving the rest of the
    config (COA mappings, fx_base, etc) untouched. Empty `ai_section`
    drops the key entirely.
    """
    new_config = {**existing_config}
    if ai_section:
        new_config["ai"] = ai_section
    else:
        new_config.pop("ai", None)
    return new_config


def render_ai_section(config: dict[str, Any], title: str) -> None:
    """Print the `.ai` portion of a config dict, or note that the
    workspace fallback is in effect."""
    ai = config.get("ai") if isinstance(config, dict) else None
    if not ai:
        out.print_warning(
            f"{title}: no AI override — using workspace default (Anthropic Haiku)."
        )
        return
    out.output(ai, title=title)
