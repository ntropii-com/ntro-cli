"""ntro workflow — create, run, list, info, test.

Phase 1.3 of N-74 reshaped this surface around a single primary verb:

    ntro workflow create --path <fs-or-uri> [--tenant T] [--entity E] [--schedule S]

Behaviour:
  - Resolves ``--path`` to an agent (auto-create-or-version) via the URI
    dispatch registry below. Phase 1 registers only the filesystem
    handler; future schemes (anthropic://, openai://, vertex://, azure:/)
    drop in additively.
  - If ``--tenant --entity`` provided, also creates a workflow row
    binding the agent to that entity (with optional --schedule / --timezone).
  - If ``--tenant`` is provided alone, only the agent is created/updated;
    no workflow.
  - For runbook paths, also triggers the worker deploy (uploads templates
    to ntro-worker via NtroOpsDeployWorkflow).

Old commands removed (clean break, no deprecation aliases):
  ``ntro workflow deploy``, ``ntro workflow deploy-status``,
  ``ntro workflow push <id> <artifact>``.
"""

from __future__ import annotations

import re
import time
from pathlib import Path
from typing import Optional, Protocol
from urllib.parse import urlparse

import typer

from ntro.workspace.exceptions import NtroError
from ntro.workspace.models.common import TaskStatus
from ntro_cli import output as out
from ntro_cli.context import get_client
from ntro_cli.helpers import load_json_input

app = typer.Typer(help="Create agents/workflows, run tasks, inspect history")


# ── URI dispatch ──────────────────────────────────────────────────────


class _PathHandler(Protocol):
    """Resolves ``--path`` to (kind, **agent_kwargs).

    Each handler receives the raw path string and either returns the
    agent kwargs to feed ``client.agents.create`` plus extra info the
    push flow needs (e.g. runbook bundle files), or raises
    ``typer.BadParameter`` if the path doesn't match its scheme.
    """

    def matches(self, path: str) -> bool: ...
    def resolve(self, path: str, client) -> dict: ...


class _RunbookFilesystemHandler:
    """``./runbooks/foo/`` → kind=runbook agent + bundle files for worker deploy."""

    def matches(self, path: str) -> bool:
        # Filesystem if no URI scheme. urlparse turns "./foo/" into
        # ParseResult(scheme='', ...) and "anthropic://x" into scheme='anthropic'.
        parsed = urlparse(path)
        return parsed.scheme in ("", "file")

    def resolve(self, path: str, client) -> dict:
        directory = Path(path).expanduser().resolve()
        if not directory.is_dir():
            raise typer.BadParameter(
                f"Path '{path}' is not a directory. Phase 1 only supports "
                f"filesystem runbook paths; URI schemes (anthropic://, "
                f"openai://, vertex://, azure:/) land in Phase 2+."
            )
        runbook_md = directory / "runbook.md"
        if not runbook_md.exists():
            raise typer.BadParameter(
                f"Path '{directory}' is missing runbook.md. A runbook "
                f"directory must contain runbook.md and a templates/ subdir."
            )
        templates_dir = directory / "templates"
        if not templates_dir.is_dir():
            raise typer.BadParameter(
                f"Path '{directory}' is missing templates/. Cannot deploy."
            )

        slug = _read_slug_from_runbook_md(runbook_md, fallback=directory.name)
        version = _read_version_from_runbook_md(runbook_md, fallback="0.1.0")
        workflow_class = _camel_case_workflow(slug)
        files = _gather_runbook_files(directory)
        if not files:
            raise typer.BadParameter(
                f"No deployable files in templates/, subledgers/, or migrations/ "
                f"under {directory}."
            )

        return {
            "kind": "runbook",
            "name": slug,
            "packageName": slug,
            "sourceRunbookSlug": slug,
            "_runbook_deploy": {
                "slug": slug,
                "version": version,
                "workflow_class": workflow_class,
                "files": files,
            },
        }


_HANDLERS: list[_PathHandler] = [_RunbookFilesystemHandler()]


def _resolve_path(path: str, client) -> dict:
    for h in _HANDLERS:
        if h.matches(path):
            return h.resolve(path, client)
    raise typer.BadParameter(
        f"No handler registered for path '{path}'. Phase 1 supports "
        f"filesystem runbook paths only."
    )


# ── ntro workflow create ──────────────────────────────────────────────


@app.command()
def create(
    path: str = typer.Option(
        ...,
        "--path",
        help=(
            "Path or URI for the agent. Filesystem path (./runbooks/foo/) for "
            "a runbook; future schemes (anthropic://, openai://, vertex://, "
            "azure:/) for external agents."
        ),
    ),
    tenant: str = typer.Option(
        ...,
        "--tenant",
        help="Tenant the agent belongs to (id or slug). Required.",
        envvar="NTRO_TENANT",
    ),
    entity: Optional[str] = typer.Option(
        None,
        "--entity",
        help=(
            "Entity to bind a workflow to. When provided, creates a workflow "
            "row in addition to the agent. Required for --schedule."
        ),
        envvar="NTRO_ENTITY",
    ),
    schedule: Optional[str] = typer.Option(
        None,
        "--schedule",
        help="Cron schedule (e.g. '0 8 5 * *'). Requires --entity.",
    ),
    timezone: Optional[str] = typer.Option(
        None,
        "--timezone",
        help="Schedule timezone (e.g. 'Europe/London'). Requires --schedule.",
    ),
    name: Optional[str] = typer.Option(
        None,
        "--name",
        help=(
            "Optional workflow display name (defaults to agent.name on read). "
            "Used for the (orgId, name) uniqueness constraint when present."
        ),
    ),
    description: Optional[str] = typer.Option(None, "--description"),
    pin_version: bool = typer.Option(
        False,
        "--pin",
        help=(
            "Pin the workflow to the version pushed by THIS command. "
            "Without --pin, agentVersionId stays null (workflow follows "
            "the agent's latest version)."
        ),
    ),
) -> None:
    """Create or update an agent, and optionally bind a workflow to an entity.

    Common flow:

        # Register agent + create workflow + deploy code in one shot
        ntro workflow create --path ./runbooks/nav-monthly/ \\
            --tenant byng --entity 4-high-court-limited \\
            --schedule "0 8 5 * *"

        # Update runbook code only (no scheduling args = no workflow)
        ntro workflow create --path ./runbooks/nav-monthly/ --tenant byng

        # Bind same agent to a second entity
        ntro workflow create --path ./runbooks/nav-monthly/ \\
            --tenant byng --entity another-entity-slug
    """
    if schedule and not entity:
        raise typer.BadParameter("--schedule requires --entity")
    if timezone and not schedule:
        raise typer.BadParameter("--timezone requires --schedule")

    try:
        client = get_client()
        resolved = _resolve_path(path, client)

        # 1. Resolve tenant id (accept slug or id).
        tenant_id = _resolve_tenant_id(client, tenant)

        # 2. Upsert the agent. Server enforces (tenantId, name) uniqueness;
        #    on conflict we fetch the existing row.
        agent_kwargs = {k: v for k, v in resolved.items() if not k.startswith("_")}
        agent = _upsert_agent(client, tenant_id=tenant_id, **agent_kwargs)
        out.print_kv("Agent", f"{agent.name} ({agent.id})")

        # 3. Push a new agent_version (kind=runbook only). External-agent
        #    pushes are no-op at this layer; their state lives on the agent
        #    row directly.
        agent_version = None
        runbook_deploy = resolved.get("_runbook_deploy")
        if agent.kind == "runbook":
            agent_version = client.agents.create_version_sync(agent.id)
            out.print_kv("Agent version", f"v{agent_version.version} ({agent_version.id})")

            # 4. Trigger worker deploy — uploads templates to ntro-worker via
            #    NtroOpsDeployWorkflow. Same mechanism that powered the old
            #    `ntro workflow deploy --runbook` command.
            deploy_result = client.runbooks.deploy_sync(
                runbook_deploy["slug"],
                tenant_slug=tenant,
                version=runbook_deploy["version"],
                workflow_class=runbook_deploy["workflow_class"],
                activity_modules=["activities"],
                files=runbook_deploy["files"],
            )
            out.print_kv("Worker deploy", f"{runbook_deploy['slug']}@{runbook_deploy['version']}")

        # 5. If --entity provided, also create the workflow row.
        if entity:
            entity_id = _resolve_entity_id(client, tenant_id, entity)
            workflow = client.workflows.create_sync(
                agentId=agent.id,
                entityId=entity_id,
                agentVersionId=agent_version.id if (pin_version and agent_version) else None,
                name=name,
                description=description,
                schedule=schedule,
                timezone=timezone,
            )
            out.output(workflow, title=f"Workflow created: {workflow.id}")
        else:
            out.print_kv(
                "Workflow",
                "(skipped — no --entity; agent only)",
            )

    except NtroError as e:
        out.print_error(str(e))
        raise typer.Exit(1)


# ── ntro workflow list / info ─────────────────────────────────────────


@app.command("list")
def list_workflows() -> None:
    """List all workflows (binding rows: agent → entity)."""
    try:
        client = get_client()
        workflows = client.workflows.list_sync()
        out.output(
            workflows,
            columns=["id", "name", "agentId", "entityId", "schedule"],
            title="Workflows",
        )
    except NtroError as e:
        out.print_error(str(e))
        raise typer.Exit(1)


@app.command()
def info(id: str = typer.Argument(help="Workflow ID")) -> None:
    """Show workflow details (with agent + entity joins)."""
    try:
        client = get_client()
        wf = client.workflows.get_sync(id)
        title = wf.name or (wf.agent.name if wf.agent else wf.id)
        out.output(wf, title=f"Workflow: {title}")
    except NtroError as e:
        out.print_error(str(e))
        raise typer.Exit(1)


# ── ntro workflow run ─────────────────────────────────────────────────


@app.command("run")
def run_workflow(
    workflow: str = typer.Argument(help="Workflow ID or name"),
    tenant: Optional[str] = typer.Option(None, "--tenant", envvar="NTRO_TENANT"),
    entity: Optional[str] = typer.Option(None, "--entity", envvar="NTRO_ENTITY"),
    period: Optional[str] = typer.Option(None, "--period"),
    priority: Optional[str] = typer.Option(None, "--priority"),
    dry_run: bool = typer.Option(False, "--dry-run"),
    wait: bool = typer.Option(False, "--wait"),
    json_input: Optional[str] = typer.Option(None, "--json"),
) -> None:
    """Trigger a workflow run."""
    try:
        if json_input:
            payload = load_json_input(json_input)
        else:
            if not tenant:
                raise typer.BadParameter("Provide --tenant or set NTRO_TENANT")
            context: dict = {}
            if period:
                context["period"] = period
            if priority:
                context["priority"] = priority
            if dry_run:
                context["dry_run"] = True
            payload = {
                "tenantId": tenant,
                "entityId": entity,
                "workflowId": workflow,
                "context": context,
            }

        client = get_client()
        task = client.tasks.create_sync(**payload)
        out.output(task, title=f"Run started: {task.id}")
        if wait:
            _poll_task(client, task.id)

    except NtroError as e:
        out.print_error(str(e))
        raise typer.Exit(1)


def _poll_task(client, task_id: str, interval: int = 3, timeout: int = 300) -> None:
    from rich.console import Console
    console = Console()
    deadline = time.monotonic() + timeout

    with console.status(f"Waiting for task {task_id}...") as status:
        while time.monotonic() < deadline:
            try:
                task = client.tasks.get_sync(task_id)
                status.update(f"[dim]{task.status}[/dim] — {task.id}")
                if task.status in (TaskStatus.COMPLETED, TaskStatus.FAILED):
                    break
                time.sleep(interval)
            except NtroError:
                time.sleep(interval)

    try:
        task = client.tasks.get_sync(task_id)
        out.output(task, title=f"Final status: {task.status}")
    except NtroError as e:
        out.print_error(str(e))


# ── helpers ───────────────────────────────────────────────────────────


def _resolve_tenant_id(client, ref: str) -> str:
    """Accept either tenant id or slug; return the canonical id."""
    tenants = client.tenants.list_sync()
    for t in tenants:
        if t.id == ref or t.slug == ref:
            return t.id
    available = ", ".join(t.slug for t in tenants)
    raise typer.BadParameter(
        f"No tenant matches '{ref}' (id or slug). Available: {available}"
    )


def _resolve_entity_id(client, tenant_id: str, ref: str) -> str:
    """Accept either entity id or slug within the tenant; return the id."""
    entities = client.entities.list_sync(tenantId=tenant_id)
    for e in entities:
        if e.id == ref or e.slug == ref:
            return e.id
    available = ", ".join(e.slug for e in entities)
    raise typer.BadParameter(
        f"No entity matches '{ref}' on tenant '{tenant_id}'. Available: {available}"
    )


def _upsert_agent(client, *, tenant_id: str, name: str, **kwargs):
    """Create the agent, or fetch the existing one on (tenantId, name) conflict."""
    try:
        return client.agents.create_sync(tenantId=tenant_id, name=name, **kwargs)
    except NtroError as e:
        # Server returns 409 with the existing agent id when the unique
        # constraint trips — pull the existing row for re-use.
        message = str(e)
        if "already exists" not in message and "409" not in message:
            raise
        for a in client.agents.list_sync(tenant_id=tenant_id):
            if a.name == name:
                return a
        raise


def _camel_case_workflow(slug: str) -> str:
    return "".join(part.capitalize() for part in slug.split("-")) + "Workflow"


_VERSION_RE = re.compile(r"^version:\s*(\S+)", flags=re.MULTILINE)
_SLUG_RE = re.compile(r"^slug:\s*(\S+)", flags=re.MULTILINE)


def _read_version_from_runbook_md(runbook_md: Path, *, fallback: str) -> str:
    text = runbook_md.read_text(encoding="utf-8")
    match = _VERSION_RE.search(text)
    return match.group(1) if match else fallback


def _read_slug_from_runbook_md(runbook_md: Path, *, fallback: str) -> str:
    text = runbook_md.read_text(encoding="utf-8")
    match = _SLUG_RE.search(text)
    return match.group(1) if match else fallback


def _gather_runbook_files(runbook_dir: Path) -> dict[str, str]:
    files: dict[str, str] = {}
    for sub in ("templates", "subledgers", "migrations"):
        sub_dir = runbook_dir / sub
        if not sub_dir.is_dir():
            continue
        for path in sub_dir.rglob("*"):
            if not path.is_file() or "__pycache__" in path.parts:
                continue
            rel = path.relative_to(runbook_dir)
            files[str(rel)] = path.read_text(encoding="utf-8")
    return files


# ── ntro workflow test (local in-memory harness — unchanged) ─────────


@app.command("test")
def test_runbook(
    runbook: Path = typer.Argument(
        ...,
        help="Path to runbook directory (containing templates/workflow.py)",
    ),
    children: list[Path] = typer.Option(
        [],
        "--child",
        help="Path to a child runbook directory (repeatable)",
    ),
    scenario: list[str] = typer.Option(
        [],
        "--scenario",
        "-s",
        help="Scenario name to run (repeatable). Default: all built-ins (happy, reject_all)",
    ),
    timeout: float = typer.Option(
        30.0, "--timeout", help="Per-scenario timeout in seconds"
    ),
    json_out: bool = typer.Option(
        False, "--json", help="Emit machine-readable JSON instead of human report"
    ),
    workflow_class: Optional[str] = typer.Option(
        None,
        "--workflow-class",
        help="Workflow class name (default: derived from runbook dir name)",
    ),
    input_json: Optional[str] = typer.Option(
        None,
        "--input",
        help="JSON for the workflow input (inline or @file). Defaults to an "
             "auto-mocked context inferred from the workflow's run() type.",
    ),
) -> None:
    """Run a runbook against the in-memory test harness."""
    import asyncio
    import importlib

    try:
        from ntro.testing import (
            BUILT_IN_SCENARIOS,
            WorkflowHarness,
            load_runbook,
            report,
        )
    except ImportError as exc:
        out.print_error(
            "ntro.testing not available — install with `pip install 'ntro[testing]'`. "
            f"({exc})"
        )
        raise typer.Exit(1)

    if not runbook.is_dir():
        out.print_error(f"Runbook directory not found: {runbook}")
        raise typer.Exit(1)

    if not scenario:
        scenarios = list(BUILT_IN_SCENARIOS.values())
    else:
        try:
            scenarios = [BUILT_IN_SCENARIOS[name] for name in scenario]
        except KeyError as exc:
            available = ", ".join(BUILT_IN_SCENARIOS)
            out.print_error(f"Unknown scenario {exc}. Available: {available}")
            raise typer.Exit(1)

    workflow_cls, _ = load_runbook(runbook, workflow_class=workflow_class)
    child_classes: list[type] = []
    for cd in children:
        c_cls, _ = load_runbook(cd)
        child_classes.append(c_cls)

    if input_json:
        wf_input = load_json_input(input_json)
        try:
            importlib.import_module(workflow_cls.__module__)
            import inspect
            params = list(inspect.signature(workflow_cls.run).parameters.values())
            if len(params) >= 2:
                input_type = params[1].annotation
                if hasattr(input_type, "model_validate"):
                    wf_input = input_type.model_validate(wf_input)
        except Exception:
            pass
    else:
        from ntro.testing.auto_mock import generate_fake
        import inspect
        params = list(inspect.signature(workflow_cls.run).parameters.values())
        if len(params) < 2:
            out.print_error(f"Cannot infer input — {workflow_cls.__name__}.run takes no payload")
            raise typer.Exit(1)
        wf_input = generate_fake(params[1].annotation)

    async def _run_all() -> list:
        results = []
        for sc in scenarios:
            async with WorkflowHarness(workflow_cls, child_workflows=child_classes) as h:
                r = await h.run(input=wf_input, scenario=sc, timeout_s=timeout)
                results.append(r)
        return results

    results = asyncio.run(_run_all())

    if json_out:
        print(report.json(results))
    else:
        print(report.human(results))

    failed = [r for r in results if r.status != "completed"]
    if failed:
        raise typer.Exit(1)
