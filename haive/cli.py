import shutil
import time
from datetime import datetime, timezone

import typer
from pydantic import ValidationError

from haive.config.manager import ConfigManager

app = typer.Typer(help="Haive — AI agent harness for software development.")
config_app = typer.Typer(help="Manage named configs.")
app.add_typer(config_app, name="config")


# ── Config subcommands ────────────────────────────────────────────────────────

@config_app.command("create")
def config_create(name: str = typer.Argument(..., help="Name for the new config.")) -> None:
    """Create a new named config."""
    try:
        ConfigManager.create(name)
        typer.echo(f"Created config '{name}'. Run 'haive config use {name}' to activate it.")
    except (ValueError, FileExistsError) as e:
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(code=1)


@config_app.command("use")
def config_use(name: str = typer.Argument(..., help="Name of the config to activate.")) -> None:
    """Activate a named config."""
    try:
        ConfigManager.use(name)
        typer.echo(f"Now using config '{name}'.")
    except FileNotFoundError as e:
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(code=1)


@config_app.command("set")
def config_set(
    key: str = typer.Argument(..., help="Config key (e.g. GITHUB_TOKEN)."),
    value: str = typer.Argument(..., help="Value to set."),
) -> None:
    """Set a KEY=VALUE in the active config."""
    try:
        ConfigManager.set_value(key, value)
        typer.echo(f"Set {key} in active config.")
    except ValueError as e:
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(code=1)


@config_app.command("edit")
def config_edit() -> None:
    """Open the active config in $EDITOR (falls back to nano)."""
    ConfigManager.edit()


@config_app.command("show")
def config_show() -> None:
    """Show the active config. Sensitive values are masked."""
    values = ConfigManager.show()
    if not values:
        typer.echo("(empty config)")
        return
    for k, v in values.items():
        typer.echo(f"{k}={v}")


@config_app.command("list")
def config_list() -> None:
    """List all named configs. The active config is marked with *."""
    configs = ConfigManager.list_configs()
    active = ConfigManager._peek_active_name()
    if not configs:
        typer.echo("No configs found. Run 'haive config create <name>' to create one.")
        return
    for name in configs:
        marker = "* " if name == active else "  "
        typer.echo(f"{marker}{name}")


# ── Preflight checks ──────────────────────────────────────────────────────────

def _check_git_on_path() -> None:
    if shutil.which("git") is None:
        typer.echo(
            "Error: 'git' is not found on PATH. Install git and ensure it is on your PATH, then try again.",
            err=True,
        )
        raise typer.Exit(code=1)


def _check_active_config() -> None:
    try:
        ConfigManager.active_config_path()
    except Exception as e:
        typer.echo(f"Error: Could not load active config — {e}", err=True)
        raise typer.Exit(code=1)


def _resolve_milestone_id(cli_value: str | None) -> str:
    if cli_value is not None:
        return cli_value
    config_value = ConfigManager.get_value("GITHUB_MILESTONE_ID")
    if config_value:
        return config_value
    typer.echo(
        "Error: No milestone specified. Pass --project <milestone> or set GITHUB_MILESTONE_ID in your active config.",
        err=True,
    )
    raise typer.Exit(code=1)


def _preflight_checks() -> None:
    _check_git_on_path()
    _check_active_config()


# ── Output formatting ─────────────────────────────────────────────────────────

def _print_dry_run_output(project, output) -> None:
    bar = "─" * 62
    title = project.title
    typer.echo(f"\n{bar}")
    typer.echo(f"  DRY RUN — {title}")
    typer.echo(f"{bar}\n")

    if output.done:
        typer.echo("Orchestrator signals: project complete. No new tasks to create.")
        return

    typer.echo(f"Tasks to create ({len(output.new_tasks)}):\n")
    for i, task in enumerate(output.new_tasks, 1):
        deps = ", ".join(task.depends_on) if task.depends_on else "none"
        typer.echo(f"  {i}. [{task.agent_role.value} / {task.complexity.value}] {task.title}")
        typer.echo(f"     {task.description}")
        typer.echo(f"     Depends on: {deps}")
        if task.acceptance_criteria:
            typer.echo("     Acceptance criteria:")
            for ac in task.acceptance_criteria:
                typer.echo(f"       - {ac}")
        if task.recovery_for:
            typer.echo(f"     Recovery for: #{task.recovery_for}")
        typer.echo()


# ── Index command ─────────────────────────────────────────────────────────────

@app.command("index")
def index(
    validate: bool = typer.Option(
        False,
        "--validate",
        is_flag=True,
        help="Validate existing agent.md files without regenerating them.",
    ),
) -> None:
    """Generate (or validate) per-directory agent.md index files."""
    import os

    _preflight_checks()
    root = os.getcwd()

    from haive.discovery.file_index_service import AgentMdGenerationError, FileIndexService
    from haive.llm.model_client import ModelClient
    from haive.llm.tier_config import TierConfig
    from haive.models.config import load_settings

    try:
        settings = load_settings()
    except Exception as e:
        typer.echo(f"Error loading config: {e}", err=True)
        raise typer.Exit(code=1)

    tier_config = TierConfig.from_settings(settings)
    model_client = ModelClient(settings)
    service = FileIndexService(model_client, tier_config.low)

    if validate:
        violations = service.validate_all(root)
        if not violations:
            typer.echo("All agent.md files are valid.")
            return
        for path, messages in sorted(violations.items()):
            typer.echo(f"\n{path}:")
            for msg in messages:
                typer.echo(f"  - {msg}")
        typer.echo(
            f"\n{len(violations)} file(s) have violations.", err=True
        )
        raise typer.Exit(code=1)

    typer.echo(f"Indexing {root} ...")
    start = time.perf_counter()
    try:
        service.generate_all(root)
    except AgentMdGenerationError as e:
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(code=1)
    elapsed = time.perf_counter() - start
    typer.echo(f"Done. agent.md files written in {elapsed:.1f}s.")


# ── Run command ───────────────────────────────────────────────────────────────

@app.command()
def run(
    project: str | None = typer.Option(
        None,
        "--project",
        help="GitHub milestone number to run. Overrides GITHUB_MILESTONE_ID in config.",
    ),
    agents: str = typer.Option(
        "agents.yaml",
        "--agents",
        help="Path to agents.yaml. Defaults to agents.yaml in the current directory.",
    ),
    examples: str = typer.Option(
        "haive/orchestration/examples.yaml",
        "--examples",
        help="Path to orchestrator examples YAML. Skipped gracefully if not found.",
    ),
) -> None:
    """Run the haive orchestrator for a milestone (dry run — prints plan, no writes)."""
    _preflight_checks()
    milestone_id = _resolve_milestone_id(project)

    from pathlib import Path

    from haive.adapters.pm.github import GitHubPMAdapter
    from haive.llm.errors import APIError
    from haive.llm.model_client import ModelClient
    from haive.llm.tier_config import TierConfig
    from haive.models.config import load_settings
    from haive.models.orchestrator import OrchestratorInput
    from haive.orchestration.example_library import ExampleLibrary
    from haive.orchestration.orchestrator import Orchestrator
    from haive.orchestration.task_view_builder import TaskViewBuilder
    from haive.persistence.state_store import StateStore
    from haive.registry.agent_registry import AgentRegistry

    try:
        settings = load_settings()
        pm = GitHubPMAdapter(settings)
        state_store = StateStore(settings)
        registry = AgentRegistry.load(agents)
        tier_config = TierConfig.from_settings(settings)
        model_client = ModelClient(settings)

        example_library: ExampleLibrary | None = None
        examples_path = Path(examples)
        if examples_path.exists():
            example_library = ExampleLibrary.load(str(examples_path))
        else:
            typer.echo(f"Note: {examples} not found — running without planning examples.")

        typer.echo(f"Fetching milestone {milestone_id}...")
        project_data = pm.get_project(milestone_id)
        tasks = pm.get_tasks(milestone_id)
        typer.echo(f"Found {len(tasks)} existing task(s).")

        state = state_store.load_or_init(milestone_id)
        since = state.last_run_at or state.created_at
        new_comments = pm.read_new_comments(milestone_id, since)

        task_views = TaskViewBuilder().build(
            tasks, state, budget_tokens=tier_config.orchestrator.context_budget
        )
        orch_input = OrchestratorInput(
            project=project_data,
            tasks=task_views,
            new_comments=new_comments,
            agent_summary=registry.get_orchestrator_summary(),
        )

        typer.echo("Calling orchestrator...")
        orchestrator = Orchestrator(model_client, tier_config, settings.max_recovery_depth, example_library)
        output = orchestrator.run_loop(orch_input)

        _print_dry_run_output(project_data, output)

    except (RuntimeError, APIError) as e:
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(code=1)
    except ValidationError as e:
        typer.echo(f"Validation error: {e}", err=True)
        raise typer.Exit(code=1)


if __name__ == "__main__":
    app()
