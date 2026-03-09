# ntro-cli — Command-line interface for the ntro platform

## Project Overview

This is the CLI for the **ntro** platform. It installs as `ntro-cli` on PyPI and registers the `ntro` binary on PATH.

| Install | Binary | What you get |
|---------|--------|-------------|
| `pip install ntro-cli` | `ntro` | CLI tool for managing the ntro platform |

The CLI is a thin interface layer over the `ntro` SDK package (`pip install ntro`). All API interaction goes through `ntro.workspace.Client`. The CLI handles argument parsing, output formatting, and interactive flows.

**Design principle:** Never put business logic or HTTP calls in the CLI. The SDK is the single source of truth for API interaction. Every CLI command is: parse args → call SDK method → format output.

---

## Architecture

```
┌─────────────────────────────┐
│          ntro-cli            │   ← This repo (Typer + Rich)
│   binary: ntro               │
└──────────────┬──────────────┘
               │ imports
               ▼
┌─────────────────────────────┐
│    ntro (separate repo)      │   ← ntro-python repo, pip install ntro
│    ntro.workspace.Client     │
└──────────────┬──────────────┘
               │ HTTP/REST
               ▼
┌─────────────────────────────┐
│  Workspace API (TypeScript)  │   ← ntro-workspace-api repo
└─────────────────────────────┘
```

### Related repos

| Repo | PyPI | Binary | Purpose |
|------|------|--------|---------|
| ntro-python | `ntro` | — | Python SDK (dependency of this repo) |
| **ntro-cli** (this) | `ntro-cli` | `ntro` | CLI tool |
| ntro-mcp | `ntro-mcp` | `ntro-mcp` | MCP server for Claude (future, also depends on `ntro`) |
| ntro-workspace-api | — | — | TypeScript/NestJS backend |

---

## Repository Structure

```
ntro-cli/
├── CLAUDE.md                        # ← This file
├── pyproject.toml
├── README.md
│
├── src/
│   └── ntro_cli/
│       ├── __init__.py
│       ├── main.py                  # Root Typer app, global flags callback, mounts groups
│       ├── context.py               # Connection-aware SDK client init, output format state
│       ├── output.py                # Output formatters (Rich tables, JSON)
│       ├── helpers.py               # load_json_input (@file or inline), common validators
│       │
│       └── commands/                # One module per command group
│           ├── __init__.py
│           ├── auth.py              # ntro auth login|list|test|set-default|whoami
│           ├── integration.py       # ntro integration add|list|info|test|discover|tenants
│           ├── tenant.py            # ntro tenant create|list|info
│           ├── entity.py            # ntro entity create|list
│           ├── workflow.py          # ntro workflow create|list|info|push|deploy|deploy-status|run
│           └── run.py               # ntro run status|list|history|incoming|pending
│
├── tests/
│   ├── unit/                        # Mocked SDK
│   └── integration/                 # Against running API
│
└── docs/
    └── cli-reference.md
```

---

## Package Configuration

```toml
# pyproject.toml
[project]
name = "ntro-cli"
version = "0.1.0"
description = "CLI for the ntro platform"
requires-python = ">=3.11"
dependencies = [
    "ntro>=0.1.0",
    "typer>=0.12",
    "rich>=13.0",
]

[project.scripts]
ntro = "ntro_cli.main:app"

[project.optional-dependencies]
dev = [
    "pytest>=8.0",
    "ruff>=0.4",
    "mypy>=1.10",
]

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["src/ntro_cli"]
```

---

## CLI Design

### Design Reference: Databricks CLI + Snowflake CLI

The ntro CLI borrows conventions from both CLIs that data engineers use daily:

- **From Snowflake CLI:** TOML config (`~/.ntro/config.toml`), `--connection` / `-c` flag,
  interactive `login` flow with `--no-interactive`, `NTRO_CONNECTIONS_<n>_<FIELD>` env var pattern
- **From Databricks CLI:** `--json` flag for complex payloads (inline or `@path/to/file.json`),
  `--output` for format switching (text/json), `--debug` flag
- **Common:** Command structure `ntro <group> <command> [args] [--flags]`, output defaults to
  text tables, JSON for piping to `jq`

### Global Flags

Every command accepts these flags (via Typer root callback):

```python
# src/ntro_cli/main.py
import typer
from typing import Optional
from ntro_cli.commands import auth, integration, tenant, entity, workflow, run

app = typer.Typer(
    name="ntro",
    help="ntro platform CLI",
    no_args_is_help=True,
)

@app.callback()
def main(
    connection: Optional[str] = typer.Option(None, "-c", "--connection", help="Connection name from config.toml", envvar="NTRO_DEFAULT_CONNECTION_NAME"),
    host: Optional[str] = typer.Option(None, help="API host URL", envvar="NTRO_HOST"),
    output: str = typer.Option("text", "-o", "--output", help="Output format: text or json"),
    debug: bool = typer.Option(False, "--debug", help="Enable debug logging"),
    log_level: Optional[str] = typer.Option(None, "--log-level", help="Log level: DEBUG, INFO, WARN, ERROR"),
    log_file: Optional[str] = typer.Option(None, "--log-file", help="Write logs to file"),
):
    """ntro platform CLI."""
    # Store in Typer context for subcommands
    ...

app.add_typer(auth.app, name="auth")
app.add_typer(integration.app, name="integration")
app.add_typer(tenant.app, name="tenant")
app.add_typer(entity.app, name="entity")
app.add_typer(workflow.app, name="workflow")
app.add_typer(run.app, name="run")
```

Usage:
```bash
ntro -c staging tenant list --output json
ntro -c production -o json workflow list --tenant acme-fund-admin
ntro --debug integration test dpc_acme_dbx
```

### The `--json` Pattern

For write commands, support `--json` alongside individual flags. Accepts inline JSON or `@path/to/file.json` (Databricks convention):

```bash
# Individual flags
ntro tenant create --name "Acme Fund Admin" --slug acme --integration dpc_123

# Inline JSON
ntro tenant create --json '{"name": "Acme Fund Admin", "slug": "acme", "data_platform_config_id": "dpc_123"}'

# From file
ntro tenant create --json @./tenant-config.json
```

Essential for `ntro integration add databricks` which has many nested config fields.

### Command Pattern

Every command: parse args/json → resolve connection → get SDK client → call SDK method → format output.

```python
# src/ntro_cli/commands/tenant.py
import typer
from typing import Optional
from ntro_cli.context import get_client, output, load_json_input

app = typer.Typer(help="Manage tenant cells (clients)")

@app.command()
def create(
    name: Optional[str] = typer.Option(None, help="Tenant name"),
    slug: Optional[str] = typer.Option(None, help="URL-safe identifier"),
    integration: Optional[str] = typer.Option(None, "--integration", help="Data platform config ID"),
    json_input: Optional[str] = typer.Option(None, "--json", help="JSON payload (inline or @file)"),
):
    """Create a new tenant (client cell)."""
    if json_input:
        payload = load_json_input(json_input)
    else:
        if not all([name, slug, integration]):
            raise typer.BadParameter("Provide --name, --slug, --integration or use --json")
        payload = {"name": name, "slug": slug, "data_platform_config_id": integration}

    client = get_client()
    tenant = client.tenants.create_sync(**payload)
    output(tenant, title=f"Tenant created: {tenant.slug}")

@app.command("list")
def list_tenants():
    """List all tenants."""
    client = get_client()
    tenants = client.tenants.list_sync()
    output(tenants, columns=["slug", "name", "status", "region", "entityCount"])

@app.command()
def info(id: str = typer.Argument(help="Tenant slug or ID")):
    """Show tenant details."""
    client = get_client()
    tenant = client.tenants.get_sync(id)
    output(tenant)
```

### Output Formatting

The `--output` / `-o` global flag controls format:

- **text** (default): Rich tables for lists, key-value panels for single objects
- **json**: Raw JSON for piping to `jq` or scripting

When `--output json` is set, output is the raw API response JSON — no wrapping, no decoration:
`ntro tenant list -o json | jq '.[].slug'`

### Auth Commands

| Command | What it does |
|---|---|
| `ntro auth login` | Interactively add/update a connection. Prompts for host, API key, default tenant. `--no-interactive` for CI/CD. Writes to `~/.ntro/config.toml`. |
| `ntro auth list` | List all configured connections with status |
| `ntro auth test` | Test the active connection (or `-c staging` to test a specific one) |
| `ntro auth set-default <n>` | Change the default connection |
| `ntro auth whoami` | Verify identity, calls `GET /me` |

### `--tenant` and `--entity` Default Resolution

Many commands require `--tenant`. Resolution order:
1. `--tenant` flag (explicit)
2. `NTRO_TENANT` env var
3. `default_tenant` in active connection (`~/.ntro/config.toml`)

Same for `--entity`: `--entity` flag > `NTRO_ENTITY` > connection's `default_entity`.

After `ntro auth login`, most commands work without flags: `ntro entity list`, `ntro workflow list`.

### `ntro integration add` is Polymorphic

```python
# src/ntro_cli/commands/integration.py
app = typer.Typer(help="Manage data platforms and integrations")
add_app = typer.Typer(help="Add a new integration")
app.add_typer(add_app, name="add")

@add_app.command()
def databricks(
    name: str = typer.Option(None),
    workspace_url: str = typer.Option(None),
    catalog: str = typer.Option(None),
    json_input: Optional[str] = typer.Option(None, "--json"),
    # ...
):
    """Register a Databricks data platform."""
    ...

@add_app.command()
def email(
    tenant: str = typer.Option(None),
    provider: str = typer.Option("microsoft-graph"),
    json_input: Optional[str] = typer.Option(None, "--json"),
    # ...
):
    """Add an email integration."""
    ...
```

### Workflow Run — Special Case

`ntro workflow run` handles file uploads and optional polling:

```python
@app.command("run")
def run_workflow(
    name: str = typer.Argument(help="Workflow name (e.g., nav-monthly, coa-import)"),
    tenant: str = typer.Option(None, help="Tenant slug"),
    entity: str = typer.Option(None, help="Entity slug"),
    period: str = typer.Option(None, help="Accounting period (e.g., 2026-03)"),
    file: Path = typer.Option(None, exists=True, help="File to upload"),
    dry_run: bool = typer.Option(False, help="Validate without committing"),
    wait: bool = typer.Option(False, help="Poll until completion"),
):
    """Trigger a workflow run."""
    client = get_client()
    task = client.tasks.create_sync(
        tenant_id=tenant, entity_id=entity, workflow_id=name,
        context={"period": period, "dry_run": dry_run}, file=file,
    )
    output(task, title=f"Workflow run started: {task.id}")
    if wait:
        poll_task(client, task.id)
```

---

## CLI Command Groups

| Group | Purpose | Key commands |
|-------|---------|-------------|
| `ntro auth` | Connection management + identity | `login`, `list`, `test`, `set-default`, `whoami` |
| `ntro integration` | Data platforms + email sources | `add databricks`, `add email`, `list`, `info`, `test`, `discover` |
| `ntro tenant` | Client cells | `create`, `list`, `info` |
| `ntro entity` | SPVs/funds within tenants | `create`, `list` |
| `ntro workflow` | Definition, deployment, triggering | `create`, `list`, `info`, `push`, `deploy`, `deploy-status`, `run` |
| `ntro run` | Inspecting executions | `status`, `list`, `history`, `incoming`, `pending` |

**Key pattern:** `ntro workflow run` = verb ("run this workflow"), `ntro run` = noun ("show me this run").

---

## Full CLI → SDK → API Mapping

| CLI Command | SDK Method | API Endpoint |
|---|---|---|
| `ntro auth whoami` | `client.identity.whoami()` | `GET /me` |
| `ntro integration add databricks` | `client.integrations.create_data_platform()` | `POST /workspace/data` |
| `ntro integration list` | `client.integrations.list_data_platforms()` | `GET /workspace/data` |
| `ntro integration info <id>` | `client.integrations.get_data_platform(id)` | `GET /workspace/data/{id}` |
| `ntro integration test <id>` | `client.integrations.test_connection(id)` | `POST /workspace/data/{id}/test` |
| `ntro integration discover <id>` | `client.integrations.discover_schemas(id)` | `GET /workspace/data/{id}/schemas` |
| `ntro tenant create` | `client.tenants.create()` | `POST /workspace/tenants` |
| `ntro tenant list` | `client.tenants.list()` | `GET /workspace/tenants` |
| `ntro tenant info <id>` | `client.tenants.get(id)` | `GET /workspace/tenants/{id}` |
| `ntro entity create` | `client.entities.create(tenant_id, ...)` | `POST /workspace/tenants/{id}/entities` |
| `ntro entity list` | `client.entities.list()` | `GET /workspace/entities` |
| `ntro workflow create` | `client.workflows.create()` | `POST /workspace/registry/workflows` |
| `ntro workflow list` | `client.workflows.list()` | `GET /workspace/registry/workflows` |
| `ntro workflow info <id>` | `client.workflows.get(id)` | `GET /workspace/registry/workflows/{id}` |
| `ntro workflow push <id>` | `client.workflows.push(id, artifact)` | `POST /workspace/registry/workflows/{id}/versions` |
| `ntro workflow deploy` | `client.deployments.create()` | `POST /workspace/registry/deployments` |
| `ntro workflow deploy-status <id>` | `client.deployments.get(id)` | `GET /workspace/registry/deployments/{id}` |
| `ntro workflow run <n>` | `client.tasks.create()` | `POST /workspace/tasks` |
| `ntro run status <id>` | `client.tasks.get(id)` | `GET /workspace/tasks/{id}` |
| `ntro run list` | `client.tasks.list_schedule()` | `GET /workspace/schedule` |
| `ntro run history` | `client.tasks.history(t, e)` | `GET /workspace/tenants/{t}/entities/{e}/tasks` |

---

## Dependencies

- **ntro** >= 0.1.0 — the SDK (from ntro-python repo)
- **typer** >= 0.12 — CLI framework
- **rich** >= 13.0 — terminal formatting (tables, panels, spinners)

Dev: pytest, ruff, mypy

---

## Domain Context

- **Tenant** = client organisation. Contains entities. `--tenant` flag or config default.
- **Entity** = SPV or fund within a tenant. `--entity` flag or config default.
- **Workflow** = repeatable process. `ntro workflow` manages definitions, `ntro workflow run` triggers execution.
- **Task** = running workflow instance. `ntro run` inspects execution status.
- **Built-in workflows** = `coa-import`, `document-ingest`, `nav-monthly`, `period-close`. Triggered via `ntro workflow run <name>`.
