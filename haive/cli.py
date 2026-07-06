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


# ── Discover command ──────────────────────────────────────────────────────────

@app.command("discover")
def discover(
    description: str = typer.Argument(..., help="What the task needs to accomplish."),
    title: str = typer.Option("", "--title", help="Short task title (defaults to first 60 chars of description)."),
    budget: int = typer.Option(16000, "--budget", help="Token budget hint passed to the discovery agent."),
    verbose: bool = typer.Option(False, "--verbose", "-v", is_flag=True, help="Print raw LLM response before parsing."),
) -> None:
    """Run the Code Discovery Agent against the current repo's agent.md tree."""
    import os
    import types

    _preflight_checks()
    root = os.getcwd()

    from haive.discovery.code_discovery_agent import CodeDiscoveryAgent
    from haive.llm.model_client import ModelClient
    from haive.llm.tier_config import TierConfig
    from haive.models.config import load_settings

    try:
        settings = load_settings()
    except Exception as e:
        typer.echo(f"Error loading config: {e}", err=True)
        raise typer.Exit(code=1)

    task_title = title or description[:60]
    task = types.SimpleNamespace(title=task_title, description=description)

    tier_config = TierConfig.from_settings(settings)
    agent = CodeDiscoveryAgent(ModelClient(settings), tier_config.low)

    if verbose:
        original_parse = agent._parse_result
        def _verbose_parse(content: str):
            typer.echo("\n── raw LLM response ──────────────────────────────────")
            typer.echo(content)
            typer.echo("──────────────────────────────────────────────────────\n")
            return original_parse(content)
        agent._parse_result = _verbose_parse  # type: ignore[method-assign]

    typer.echo(f'Discovering for: "{task_title}"\n')
    start = time.perf_counter()
    result = agent.discover(task, root, budget)
    elapsed = time.perf_counter() - start

    typer.echo(f"Status: {result.status}  ({elapsed:.1f}s)\n")

    if not result.sections:
        typer.echo("No relevant sections found.")
        return

    typer.echo(f"Sections ({len(result.sections)}, most relevant first):\n")
    for i, s in enumerate(result.sections, 1):
        location = s.file
        if s.symbol:
            location += f"  ·  {s.symbol}"
        if s.start_line and s.end_line:
            location += f" — {s.start_line}-{s.end_line}"
        elif s.full:
            location += "  ·  full file"
        typer.echo(f"  {i}. {location}")
        typer.echo(f"     {s.reason}")
        typer.echo()


# ── Load command ─────────────────────────────────────────────────────────────

@app.command("load")
def load(
    description: str = typer.Argument(..., help="What the task needs to accomplish."),
    title: str = typer.Option("", "--title", help="Short task title (defaults to first 60 chars of description)."),
    budget: int = typer.Option(16000, "--budget", help="Token budget for section loading."),
) -> None:
    """Discover relevant files and load their source content (discover + load pipeline)."""
    import os
    import types

    _preflight_checks()
    root = os.getcwd()

    from haive.discovery.code_discovery_agent import CodeDiscoveryAgent
    from haive.discovery.file_index_service import FileIndexService
    from haive.llm.model_client import ModelClient
    from haive.llm.tier_config import TierConfig
    from haive.llm.token_counter import TokenCounter
    from haive.models.config import load_settings

    try:
        settings = load_settings()
    except Exception as e:
        typer.echo(f"Error loading config: {e}", err=True)
        raise typer.Exit(code=1)

    task_title = title or description[:60]
    task = types.SimpleNamespace(title=task_title, description=description)

    tier_config = TierConfig.from_settings(settings)
    client = ModelClient(settings)
    agent = CodeDiscoveryAgent(client, tier_config.low)
    service = FileIndexService(client, tier_config.low)

    typer.echo(f'Loading context for: "{task_title}"\n')

    start = time.perf_counter()
    result = agent.discover(task, root, budget)
    discover_elapsed = time.perf_counter() - start

    typer.echo(f"Discovery: {result.status}  ({discover_elapsed:.1f}s)")

    if not result.sections:
        typer.echo("No relevant sections found.")
        return

    typer.echo(f"Sections found: {len(result.sections)}  |  budget: {budget:,} tokens\n")

    try:
        loaded = service.load_sections(result, root, budget)
    except FileNotFoundError as e:
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(code=1)

    tokens_used = sum(TokenCounter.estimate(s.source) for s in loaded)
    bar = "─" * 60

    for i, section in enumerate(loaded, 1):
        typer.echo(f"{bar}")
        typer.echo(f"  {i}/{len(loaded)}  {section.file}  |  {TokenCounter.estimate(section.source):,} tokens")
        typer.echo(f"  {section.reason}")
        typer.echo(f"{bar}")
        typer.echo(section.source)

    typer.echo(f"{bar}")
    dropped = len(result.sections) - len(loaded)
    drop_note = f"  |  {dropped} dropped (budget)" if dropped else ""
    typer.echo(f"Loaded: {len(loaded)}/{len(result.sections)} sections  |  {tokens_used:,}/{budget:,} tokens used{drop_note}")


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
    dry_run: bool = typer.Option(
        False,
        "--dry-run",
        is_flag=True,
        help="Print what would happen without writing files, creating PRs, or calling adapter write methods.",
    ),
    no_merge: bool = typer.Option(
        False,
        "--no-merge",
        is_flag=True,
        help="Create task PRs but do not auto-merge them. Leaves PRs open for human review.",
    ),
) -> None:
    """Run the haive agent harness for a project milestone.

    Loops automatically across waves (planning, executing, replanning) up to
    settings.max_waves_per_run, stopping early when the project is done or
    the orchestrator has no further automatic action to take.
    """
    import os
    import subprocess
    from datetime import datetime, timezone
    from pathlib import Path

    _preflight_checks()
    milestone_id = _resolve_milestone_id(project)
    root = os.getcwd()

    from haive.adapters.pm.github import GitHubPMAdapter
    from haive.adapters.vcs.github import GitHubVCSAdapter
    from haive.discovery.code_discovery_agent import CodeDiscoveryAgent
    from haive.discovery.file_index_service import FileIndexService
    from haive.execution.review_agent import ReviewAgent
    from haive.execution.task_executor import TaskExecutor
    from haive.llm.errors import APIError
    from haive.llm.model_client import ModelClient
    from haive.llm.tier_config import TierConfig
    from haive.llm.token_counter import TokenCounter
    from haive.models.config import load_settings
    from haive.models.enums import AgentRole, TaskStatus
    from haive.models.orchestrator import OrchestratorInput
    from haive.models.task import Task, TaskExecutionRecord
    from haive.observability.setup import setup_observability
    from haive.observability.spans import run_span
    from haive.orchestration.example_library import ExampleLibrary
    from haive.orchestration.orchestrator import Orchestrator, OrchestratorStalledError
    from haive.orchestration.task_scheduler import TaskScheduler
    from haive.orchestration.task_view_builder import TaskViewBuilder
    from haive.persistence.state_store import StateStore
    from haive.registry.agent_registry import AgentRegistry

    try:
        settings = load_settings()
        settings.dry_run = dry_run
        settings.auto_merge = not no_merge

        if settings.observability_enabled:
            setup_observability(settings)

        registry = AgentRegistry.load(agents)
        tier_config = TierConfig.from_settings(settings)
        model_client = ModelClient(settings)
        pm = GitHubPMAdapter(settings)
        vcs = GitHubVCSAdapter(settings)
        state_store = StateStore(settings)

        # agent.md preflight check
        if not list(Path(root).rglob("agent.md")):
            typer.secho(
                "Error: No agent.md files found. Run 'haive index' first to generate them.",
                fg="red",
                err=True,
            )
            raise typer.Exit(code=1)

        discovery_agent = CodeDiscoveryAgent(model_client, tier_config.low)
        file_index = FileIndexService(model_client, tier_config.low)

        try:
            project_branch = subprocess.check_output(
                ["git", "branch", "--show-current"], cwd=root
            ).decode().strip() or "main"
        except subprocess.CalledProcessError:
            project_branch = "main"

        example_library: ExampleLibrary | None = None
        examples_path = Path(examples)
        if examples_path.exists():
            example_library = ExampleLibrary.load(str(examples_path))
        else:
            typer.echo(f"Note: {examples} not found — running without planning examples.")

        # Build executor components once — stable across every wave in this invocation.
        reviewer_config = registry.get_agent(AgentRole.CODE_REVIEWER_AGENT)
        reviewer_system_prompt = Path(root, reviewer_config.system_prompt).read_text(encoding="utf-8")
        guidelines_candidates = [Path(root, "GUIDELINES.md"), Path(root, "guidelines.md")]
        guidelines = next(
            (p.read_text(encoding="utf-8") for p in guidelines_candidates if p.exists()), ""
        )
        review_agent = ReviewAgent(model_client, reviewer_system_prompt, guidelines, root)
        executor = TaskExecutor(
            model_client, tier_config, review_agent, root, project_branch,
            auto_merge=settings.auto_merge,
            on_status=typer.echo,
        )

        project_data = pm.get_project(milestone_id)

        with run_span(milestone_id):
            for wave_num in range(1, settings.max_waves_per_run + 1):
                typer.secho(f"\n--- Wave {wave_num} ---", bold=True)
                typer.echo(f"Fetching milestone {milestone_id}...")
                tasks = pm.get_tasks(milestone_id)
                typer.echo(f"Found {len(tasks)} existing task(s).")

                state = state_store.load_or_init(milestone_id)

                # Reconcile tasks stuck awaiting a manual merge: if a human has since
                # merged the PR, mark the task complete instead of leaving it stuck
                # forever. Only ever queries tasks that already have a stored pr_id
                # (i.e. passed review) — genuine review failures cost no extra calls.
                reconciled = False
                for t in tasks:
                    if t.status != TaskStatus.AWAITING_MERGE:
                        continue
                    record = state.tasks.get(t.task_id)
                    if not record or not record.pr_id:
                        continue
                    try:
                        if vcs.is_pr_merged(record.pr_id):
                            pm.update_status(t.task_id, TaskStatus.COMPLETE)
                            typer.echo(f"  [#{t.task_id}] PR #{record.pr_id} was merged — marking complete.")
                            reconciled = True
                    except RuntimeError as exc:
                        typer.echo(f"  [#{t.task_id}] Could not check PR #{record.pr_id} status: {exc}")
                if reconciled:
                    tasks = pm.get_tasks(milestone_id)

                since = state.last_run_at or state.created_at
                new_comments = pm.read_new_comments(milestone_id, since)

                state.last_run_at = datetime.now(tz=timezone.utc)
                if not dry_run:
                    state_store.save(state)

                pending_tasks = [t for t in tasks if t.status == TaskStatus.PENDING]
                new_task_objects: list[Task] = []

                if pending_tasks:
                    # Pending tasks exist — skip the orchestrator and execute them.
                    if dry_run:
                        typer.echo(f"[dry-run] {len(pending_tasks)} pending task(s) would be scheduled:")
                        for t in pending_tasks:
                            typer.echo(f"  - #{t.task_id}: {t.title}")
                        return
                    typer.echo(f"Scheduling {len(pending_tasks)} pending task(s)...")
                else:
                    repo_map = file_index.read_repo_map(root)
                    task_view_budget = tier_config.orchestrator.context_budget - TokenCounter.estimate(repo_map)
                    task_views = TaskViewBuilder().build(
                        tasks, state, budget_tokens=task_view_budget
                    )
                    orch_input = OrchestratorInput(
                        project=project_data,
                        tasks=task_views,
                        new_comments=new_comments,
                        agent_summary=registry.get_orchestrator_summary(),
                        repo_map=repo_map,
                    )

                    typer.echo("Calling orchestrator...")
                    orchestrator = Orchestrator(model_client, tier_config, settings.max_recovery_depth, example_library)
                    try:
                        output = orchestrator.run_loop(orch_input)
                    except OrchestratorStalledError as e:
                        typer.echo(f"\n{e} — waiting on human input.")
                        return

                    if dry_run:
                        _print_dry_run_output(project_data, output)
                        return

                    if output.done:
                        pr_url = vcs.create_project_pr(
                            project_branch,
                            "main",
                            f"Project complete: {project_data.title}",
                            "All tasks complete — merging project branch to main.",
                        )
                        typer.echo(f"\nProject complete. PR created: {pr_url}")
                        return

                    # Create new tasks and resolve "new:N" dependency refs.
                    id_map: dict[str, str] = {}
                    for i, new_task in enumerate(output.new_tasks):
                        created = pm.create_task(milestone_id, new_task)
                        id_map[f"new:{i}"] = created.task_id
                        new_task_objects.append(created)
                        typer.echo(f"  Created task #{created.task_id}: {created.title}")

                    for i, new_task in enumerate(output.new_tasks):
                        if new_task.depends_on:
                            resolved = [id_map.get(dep, dep) for dep in new_task.depends_on]
                            pm.set_dependency(new_task_objects[i].task_id, resolved)
                            new_task_objects[i] = new_task_objects[i].model_copy(
                                update={"depends_on": resolved}
                            )

                # Combine pre-existing pending tasks with newly created ones.
                # Newly created tasks come from the adapter directly (not re-read from GitHub)
                # because Projects v2 GraphQL does not reflect new items immediately.
                all_tasks = pending_tasks + new_task_objects

                wave_complete = 0
                wave_needs_review = 0
                wave_awaiting_merge = 0
                wave_blocked = 0

                def on_task_complete(record: TaskExecutionRecord) -> None:
                    nonlocal wave_complete, wave_needs_review, wave_awaiting_merge
                    passed = record.verdict is not None and record.verdict.passed
                    if passed and record.merged:
                        wave_complete += 1
                        typer.secho(f"  ✓ Task #{record.task_id} — complete", fg="green")
                    elif passed and not record.merged:
                        wave_awaiting_merge += 1
                        typer.secho(f"  ⏳ Task #{record.task_id} — awaiting merge", fg="yellow")
                    else:
                        wave_needs_review += 1
                        typer.secho(f"  ✗ Task #{record.task_id} — needs-human-review", fg="red")

                def executor_factory(task):  # type: ignore[no-untyped-def]
                    return executor.run(
                        task, milestone_id, state,
                        discovery_agent, file_index, registry, pm, vcs, state_store,
                    )

                typer.echo("\nRunning tasks...")
                scheduler = TaskScheduler()
                scheduler.start(all_tasks, executor_factory, pm, on_complete=on_task_complete)

                final_tasks = pm.get_tasks(milestone_id)
                wave_blocked = sum(1 for t in final_tasks if t.status == TaskStatus.BLOCKED)

                typer.secho(
                    f"\nWave {wave_num} complete — "
                    f"{wave_complete} complete, "
                    f"{wave_needs_review} needs-human-review, "
                    f"{wave_awaiting_merge} awaiting-merge, "
                    f"{wave_blocked} blocked",
                    bold=True,
                )

            typer.echo(
                f"\nReached the automatic wave limit ({settings.max_waves_per_run}) for this run. "
                "Re-run 'haive run' to continue."
            )

    except (RuntimeError, APIError) as e:
        typer.secho(f"Error: {e}", fg="red", err=True)
        raise typer.Exit(code=1)
    except ValidationError as e:
        typer.secho(f"Validation error: {e}", fg="red", err=True)
        raise typer.Exit(code=1)


# ── Prune-branches command ────────────────────────────────────────────────────

@app.command("prune-branches")
def prune_branches(
    yes: bool = typer.Option(
        False,
        "--yes", "-y",
        is_flag=True,
        help="Delete without confirmation prompt.",
    ),
) -> None:
    """List haive/task-* branches whose PRs have been merged, and delete them."""
    _preflight_checks()

    from haive.adapters.vcs.github import GitHubVCSAdapter
    from haive.models.config import load_settings

    try:
        settings = load_settings()
        vcs = GitHubVCSAdapter(settings)

        branches = vcs.list_task_branches("haive/task-")
        merged: list[tuple[str, str]] = []
        unmerged_closed: list[tuple[str, str]] = []
        for b in branches:
            info = vcs.find_pr_for_branch(b)
            if info is None:
                continue
            pr_id, is_merged = info
            if is_merged:
                merged.append((b, pr_id))
            else:
                unmerged_closed.append((b, pr_id))

        if unmerged_closed:
            typer.echo(
                f"{len(unmerged_closed)} branch(es) have a closed-but-unmerged PR — "
                "not pruned automatically, review manually:"
            )
            for b, pr_id in unmerged_closed:
                typer.echo(f"  - {b}  (PR #{pr_id}, closed without merging)")

        if not merged:
            typer.echo("No merged task branches to prune.")
            return

        typer.echo(f"{len(merged)} merged task branch(es) eligible for deletion:")
        for b, pr_id in merged:
            typer.echo(f"  - {b}  (PR #{pr_id})")

        if not yes and not typer.confirm(f"Delete these {len(merged)} branch(es)?"):
            typer.echo("Aborted — no branches deleted.")
            return

        for b, _ in merged:
            vcs.delete_branch(b)
            typer.echo(f"  Deleted {b}")

    except RuntimeError as e:
        typer.secho(f"Error: {e}", fg="red", err=True)
        raise typer.Exit(code=1)


if __name__ == "__main__":
    app()
