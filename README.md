# ntro-cli

Command-line interface for the [ntro platform](https://ntropii.com) — fund operations automation for private markets firms.

The CLI is a thin layer over the `ntro` Python SDK. Every command follows the pattern: parse args → call SDK → format output. No business logic lives here.

---

## Installation

### Prerequisites

- Python 3.11+
- The `ntro` SDK (installed automatically as a dependency)

### Development install (local workspace)

```bash
# Create a shared venv (once)
uv venv ~/.ntro-dev --python 3.12
source ~/.ntro-dev/bin/activate   # or add ~/.ntro-dev/bin to PATH

# Install the SDK (editable)
uv pip install -e ~/ntropii/ntro-python

# Install the CLI (editable)
uv pip install -e ~/ntropii/ntro-cli
```

Verify:

```bash
ntro --help
```

### Production install (once published to PyPI)

```bash
pip install ntro-cli
```

---

## Quick start

```bash
# 1. Add a connection (interactive)
ntro auth login

# 2. Verify identity
ntro auth whoami

# 3. List tenants
ntro tenant list

# 4. Run a workflow
ntro workflow run nav-monthly --tenant acme-fund-admin --entity acme-spv1 --period 2026-03
```

---

## Configuration

The CLI reads `~/.ntro/config.toml`. Run `ntro auth login` to create it interactively, or write it manually:

```toml
default_connection_name = "local"

[connections.local]
host = "http://localhost:3000/v1"
api_key = "ntro_dev_key"
default_tenant = "acme-fund-admin"

[connections.production]
host = "https://api.ntropii.com/v1"
api_key = "your-api-key-here"
```

### Override at runtime

| Method | Example |
|---|---|
| Connection flag | `ntro -c production tenant list` |
| Host flag | `ntro --host http://localhost:3000/v1 tenant list` |
| Env vars | `NTRO_HOST=http://localhost:3000/v1 ntro tenant list` |

---

## Global flags

All commands accept these flags **before** the subcommand:

```
ntro [OPTIONS] COMMAND [ARGS]...

Options:
  -c, --connection TEXT   Connection name from config.toml
                          [env: NTRO_DEFAULT_CONNECTION_NAME]
  --host TEXT             Override API host URL
                          [env: NTRO_HOST]
  -o, --output TEXT       Output format: text or json  [default: text]
  --debug                 Enable debug logging
  --log-level TEXT        DEBUG, INFO, WARN, ERROR
```

Example:

```bash
ntro -c staging -o json tenant list
```

---

## Command reference

### `ntro auth`

```bash
ntro auth login                        # Interactive — prompts for host, api-key, default tenant
ntro auth login --no-interactive \     # Non-interactive (CI/CD)
  --name local \
  --host http://localhost:3000/v1 \
  --api-key ntro_dev_key

ntro auth list                         # List all configured connections
ntro auth test                         # Test the active connection
ntro auth test -c staging              # Test a specific connection
ntro auth set-default production       # Change the default connection
ntro auth whoami                       # Show current user identity
```

---

### `ntro integration`

```bash
# Register a Databricks data platform
ntro integration add databricks \
  --name "Acme Databricks UK" \
  --workspace-url https://adb-1234.azuredatabricks.net \
  --catalog fund_ops \
  --client-id <id> \
  --client-secret <secret> \
  --region UK-South

# Or use --json for the full payload
ntro integration add databricks --json @./databricks-config.json

# Add an email integration
ntro integration add email --tenant acme-fund-admin

# List / inspect
ntro integration list
ntro integration info <id>
ntro integration test <id>
ntro integration discover <id>         # List schemas in the data platform
```

---

### `ntro tenant`

```bash
ntro tenant create --name "Acme Fund Administration" --slug acme-fund-admin --integration <dpc-id>
ntro tenant create --json '{"name":"Acme","slug":"acme","dataPlatformConfigId":"dpc_123"}'

ntro tenant list
ntro tenant info acme-fund-admin
```

---

### `ntro entity`

```bash
ntro entity create \
  --name "Acme Commercial SPV 1" \
  --slug acme-commercial-spv1 \
  --tenant acme-fund-admin \
  --type real-estate-spv \
  --jurisdiction Jersey \
  --currency GBP

ntro entity list
ntro entity list --tenant acme-fund-admin    # Filter by tenant
```

Tenant resolution order: `--tenant` flag → `NTRO_TENANT` env var → `default_tenant` in config.

---

### `ntro workflow`

```bash
# Register a workflow definition
ntro workflow create \
  --name nav-monthly \
  --description "Monthly NAV pipeline" \
  --schedule "0 8 5 * *" \
  --timezone Europe/London

ntro workflow list
ntro workflow info <id>

# Push a new version artifact
ntro workflow push <workflow-id> ./nav-monthly-v2.zip

# Deploy a version to a tenant
ntro workflow deploy --workflow <id> --version <version-id> --tenant acme-fund-admin
ntro workflow deploy-status <deployment-id>

# Trigger a run
ntro workflow run nav-monthly \
  --tenant acme-fund-admin \
  --entity acme-spv1 \
  --period 2026-03

ntro workflow run nav-monthly --tenant acme-fund-admin --wait   # Poll until complete
ntro workflow run nav-monthly --tenant acme-fund-admin --dry-run
```

#### `ntro workflow test` — local inner-loop tests

Run a runbook against an in-memory Temporal with auto-mocked activities. No deploy, no docker — sub-second startup. Catches the same workflow bugs the deployed e2e flow would, but in seconds rather than minutes.

```bash
# Single workflow (no children)
ntro workflow test ./runbooks/document-ingest

# Parent + children (each --child registered alongside the parent)
ntro workflow test ./runbooks/nav-monthly \
  --child ./runbooks/document-ingest \
  --child ./runbooks/nav-monthly-journals

# Specific scenarios + machine-readable output for CI
ntro workflow test ./runbooks/nav-monthly --scenario happy --json
```

Output:
```
✓  happy        (0.86s)
    [ 0.13s] submit_file  hly-7a820232  signal=tb_submitted, source=xero-trial-balance
    [ 0.36s] review       ument-ingest  response=approved
    [ 0.47s] review       hly-journals  response=approved
    [ 0.86s] done         hly-7a820232
✓  reject_all   (0.45s)
summary: 2 passed, 0 failed (of 2)
```

What's auto-mocked: activity returns (from Pydantic types), HITL approvals (per scenario), submit_file signals (with fake `document_ref`/slugs derived from the workflow's advertised args). See [`ntro` SDK README — Testing workflows](../ntro-python/README.md#testing-workflows-ntrotesting) for the full surface and how to define custom scenarios.

Requires `ntro[testing]` (installed automatically as a CLI dependency).

---

### `ntro run`

```bash
ntro run status <task-id>              # Show run status and step progress
ntro run list                          # Show scheduled / active runs
ntro run history \                     # Show run history for an entity
  --tenant acme-fund-admin \
  --entity acme-spv1
ntro run incoming                      # Show queued runs
ntro run pending                       # Show runs awaiting action
```

---

## Output formats

```bash
# Default: Rich tables (lists) and panels (single objects)
ntro tenant list

# JSON — pipe to jq for scripting
ntro -o json tenant list | jq '.[].slug'
ntro -o json auth whoami | jq .email
```

---

## The `--json` pattern

Write commands accept `--json` for complex payloads:

```bash
# Inline
ntro tenant create --json '{"name":"Acme","slug":"acme","dataPlatformConfigId":"dpc_123"}'

# From file (@ prefix, Databricks CLI convention)
ntro integration add databricks --json @./databricks.json
```

---

## Related packages

| Package | Description |
|---|---|
| `ntro` | Python SDK (dependency of this package) |
| `ntro-mcp` | MCP server — use ntro from Claude Desktop / claude.ai |
