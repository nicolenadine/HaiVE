import json
import shutil
import time
from datetime import datetime, timezone
from enum import Enum
from importlib.resources import files as _resource_files

import typer
from pydantic import ValidationError

from haive.config.manager import ConfigManager

_DEFAULT_AGENTS_PATH = str(_resource_files("haive") / "resources" / "agents.yaml")
_DEFAULT_EXAMPLES_PATH = str(_resource_files("haive") / "orchestration" / "examples.yaml")


class MilestoneRunOutcome(str, Enum):
    """What happened at the end of one _run_milestone() call.

    run() ignores this (it only ever processes one milestone and prints
    everything it needs internally); run-all() uses it to decide whether to
    advance to the next milestone in the queue or stop there.
    """

    DONE_MERGED = "done_merged"                # milestone done, final PR merged — safe to advance
    DONE_AWAITING_MERGE = "done_awaiting_merge"  # milestone done, final PR open — gated, or auto-merge failed
    WAVE_LIMIT_REACHED = "wave_limit_reached"    # not done, ran out of waves this invocation
    STALLED = "stalled"                          # OrchestratorStalledError — no automatic action possible
    DRY_RUN_PREVIEW = "dry_run_preview"          # --dry-run showed a preview; nothing was done

app = typer.Typer(
    help=(
        "Haive — a multi-provider AI agent harness that coordinates specialized "
        "sub-agents through GitHub Issues and Projects to complete software "
        "development tasks, with a full review-and-retry loop before merging.\n\n"
        "First time? Run 'haive config create <name>', set GITHUB_TOKEN/GITHUB_REPO, "
        "then 'haive project setup' before 'haive run'. See README.md for details."
    )
)
config_app = typer.Typer(
    help="Manage named configs. Run 'haive config --help' for subcommands (create, use, set, show, list, edit, delete)."
)
app.add_typer(config_app, name="config")
project_app = typer.Typer(
    help="Manage the GitHub Project board haive coordinates through. Run 'haive project --help' for subcommands (setup)."
)
app.add_typer(project_app, name="project")


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
    """Open the active config in $EDITOR (falls back to vim)."""
    ConfigManager.edit()


@config_app.command("show")
def config_show(
    json_flag: bool = typer.Option(False, "--json", is_flag=True, help="Output as JSON.")
) -> None:
    """Show the active config. Sensitive values are masked."""
    values = ConfigManager.show()
    if json_flag:
        typer.echo(json.dumps(values))
    else:
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


@config_app.command("delete")
def config_delete(name: str = typer.Argument(..., help="Name of the config to delete.")) -> None:
    """Delete a named config."""
    try:
        ConfigManager.delete(name)
        typer.echo(f"Deleted config '{name}'.")
    except (FileNotFoundError, ValueError) as e:
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(code=1)


# ── Project subcommands ───────────────────────────────────────────────────────

@project_app.command("setup")
def project_setup(
    title: str = typer.Option(
        None, "--title", help='Project title (default: "<repo> Haive").',
    ),
) -> None:
    """Create or configure a Haive-compatible GitHub Project v2 board.

    Uses GITHUB_TOKEN/GITHUB_REPO from the active config. Idempotent — safe
    to re-run against an already-configured board. On success, writes the
    board's project number to GITHUB_PROJECT_ID in the active config.
    """
    _preflight_checks()

    from haive.adapters.pm.board_setup import setup_board
    from haive.models.config import load_settings

    try:
        settings = load_settings()
    except Exception as e:
        typer.echo(f"Error loading config: {e}", err=True)
        raise typer.Exit(code=1)

    if not settings.github_token or not settings.github_repo:
        typer.echo(
            "Error: GITHUB_TOKEN and GITHUB_REPO must be set in the active config first.",
            err=True,
        )
        raise typer.Exit(code=1)
    if "/" not in settings.github_repo:
        typer.echo(
            f"Error: GITHUB_REPO must be in 'owner/repo' format, got: {settings.github_repo!r}",
            err=True,
        )
        raise typer.Exit(code=1)

    owner, repo = settings.github_repo.split("/", 1)
    board_title = title or f"{repo} Haive"

    try:
        result = setup_board(settings.github_token, owner, repo, board_title)
    except RuntimeError as e:
        typer.secho(f"Error: {e}", fg="red", err=True)
        raise typer.Exit(code=1)

    typer.echo(
        f"{'Created' if result.created_project else 'Reusing existing'} project "
        f"#{result.project_number}: {result.project_url}"
    )
    if result.fields_created:
        typer.echo(f"Created field(s): {', '.join(result.fields_created)}")
    if result.fields_already_existing:
        typer.echo(f"Field(s) already present: {', '.join(result.fields_already_existing)}")
    typer.echo(
        "Status options updated to match haive's TaskStatus values."
        if result.status_updated
        else "Status options already correct."
    )

    if not result.verified:
        typer.secho("Verification failed:", fg="red", err=True)
        for issue in result.verification_issues:
            typer.secho(f"  - {issue}", fg="red", err=True)
        raise typer.Exit(code=1)

    ConfigManager.set_value("GITHUB_PROJECT_ID", str(result.project_number))
    typer.echo(f"Verified. GITHUB_PROJECT_ID set to {result.project_number} in the active config.")


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

def _close_finished_milestone(pm, milestone_id: str) -> None:
    """Best-effort end-of-milestone cleanup — closing completed tasks and
    the milestone itself is cosmetic tidiness, not required for
    correctness. A milestone whose final PR already merged must still be
    reported done even if this fails (e.g. a transient GitHub API error);
    the next invocation will just find things still open and retry the
    cleanup then, rather than the whole run crashing over a non-critical
    step after the actual, important work already succeeded.
    """
    try:
        pm.close_completed_tasks(milestone_id)
        pm.close_milestone(milestone_id)
    except RuntimeError as exc:
        typer.echo(f"Warning: could not close completed tasks/milestone: {exc}")


def _format_recovery_lineage_summary(
    stalled_task_id: str,
    tasks: list,
    state,
    max_recovery_depth: int,
) -> str:
    """Summarize a maxed-out recovery chain for a human reading the GitHub issue.

    Walks recovery_for pointers back to the root task, root-first, so a human
    opening stalled_task_id's issue sees every generation's outcome without
    having to trace the chain themselves via git/GitHub history.
    """
    tasks_by_id = {t.task_id: t for t in tasks}

    chain: list = []
    current_id: str | None = stalled_task_id
    while current_id is not None:
        task = tasks_by_id.get(current_id)
        if task is None:
            break
        chain.append(task)
        current_id = task.recovery_for
    chain.reverse()

    lines = [
        "**haive: recovery chain exhausted — max_recovery_depth reached**",
        "",
        "This task is part of a recovery chain that has repeatedly failed. "
        f"No further automatic recovery will be attempted (max_recovery_depth = {max_recovery_depth}).",
        "",
    ]
    for task in chain:
        record = state.tasks.get(task.task_id)
        reason = record.verdict.reason if record and record.verdict else "no verdict recorded"
        attempts = record.total_attempts if record else 0
        lines.append(
            f"- Generation {task.lineage_depth} (#{task.task_id}): {reason} ({attempts} attempt(s))"
        )
    lines.append("")
    lines.append(
        "Human review is needed to break the chain — retrying is unlikely to help further. "
        "Once you've reviewed and corrected the underlying issue (e.g. posted a comment here "
        f"with the fix), run `haive run --unstall {stalled_task_id}` (or add `--unstall "
        f"{stalled_task_id}` to `haive run-all`) to authorize one recovery attempt beyond "
        "max_recovery_depth for this task's lineage specifically."
    )
    return "\n".join(lines)


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
    """Generate (or validate) per-directory agent.md index files.

    Required before 'haive run' — task agents navigate this index to find
    relevant code instead of scanning the whole repo. Regenerates every
    directory unconditionally (an LLM call each); 'haive run' itself keeps
    the index incrementally up to date after each task, so you shouldn't
    need to re-run this by hand except after manual edits outside haive.
    A brand-new, genuinely empty repo gets a placeholder agent.md instead
    (no LLM call) so its first (typically scaffolding) task can still run.
    """
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
        indexed = service.generate_all(root)
    except AgentMdGenerationError as e:
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(code=1)
    elapsed = time.perf_counter() - start
    if indexed == 0:
        typer.echo(
            "No source files found — wrote a placeholder agent.md so "
            f"'haive run' can bootstrap this project's first task. ({elapsed:.1f}s)"
        )
    else:
        typer.echo(f"Done. {indexed} agent.md file(s) written in {elapsed:.1f}s.")


# ── Discover command ──────────────────────────────────────────────────────────

@app.command("discover")
def discover(
    description: str = typer.Argument(..., help="What the task needs to accomplish."),
    title: str = typer.Option("", "--title", help="Short task title (defaults to first 60 chars of description)."),
    budget: int = typer.Option(16000, "--budget", help="Token budget hint passed to the discovery agent."),
    verbose: bool = typer.Option(False, "--verbose", "-v", is_flag=True, help="Print raw LLM response before parsing."),
) -> None:
    """Run the Code Discovery Agent standalone, without executing a task.

    Useful for inspecting or debugging what context a given task description
    would surface before actually running it — not part of the normal
    'haive run' workflow, which does this internally per task.
    """
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
    agent = CodeDiscoveryAgent(ModelClient(settings), tier_config.low, escalation_tier=tier_config.medium)

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
    """Discover relevant files and print their loaded source content.

    Combines 'discover' with the same section-loading/budget logic 'haive run'
    uses internally to assemble a task's context — useful for previewing
    exactly what an agent would see, without executing anything.
    """
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
    agent = CodeDiscoveryAgent(client, tier_config.low, escalation_tier=tier_config.medium)
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

def _run_milestone(
    milestone_id: str,
    agents: str,
    examples: str,
    dry_run: bool,
    no_merge: bool,
    quiet: bool,
    *,
    auto_merge_final_pr: bool,
    command_name: str = "haive run",
    project_data=None,
    unstall_task_id: str | None = None,
) -> MilestoneRunOutcome:
    """Run the harness against a single milestone until it's done, stalls,
    or runs out of waves for this invocation. Shared by both `run` (one
    milestone, final PR never auto-merged) and `run-all` (a queue of
    milestones, where auto_merge_final_pr is decided per-milestone by its
    own #Checkpoint marker).

    project_data lets a caller that already fetched the Project (run-all
    does, to read .checkpoint before deciding auto_merge_final_pr) pass it
    through instead of triggering a second, redundant fetch here.

    unstall_task_id authorizes one recovery attempt beyond max_recovery_depth
    for that specific task's lineage only — the escape hatch for a chain that
    hit the depth cap, after a human has reviewed and corrected it. Every
    other lineage is still held to the normal limit.
    """
    import os
    from pathlib import Path

    root = os.getcwd()

    from haive.adapters.pm.github import GitHubPMAdapter
    from haive.adapters.vcs.github import GitHubVCSAdapter
    from haive.discovery.code_discovery_agent import CodeDiscoveryAgent
    from haive.discovery.file_index_service import FileIndexService
    from haive.execution.command_runner import CommandRunner
    from haive.execution.dependency_approval import DependencyApprovalGate
    from haive.execution.execution_verifier import ExecutionVerifier
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
        settings.auto_merge = not no_merge

        if settings.observability_enabled:
            setup_observability(settings)

        try:
            registry = AgentRegistry.load(agents)
        except FileNotFoundError as e:
            typer.secho(f"Error: agents.yaml not found at '{agents}' ({e}).", fg="red", err=True)
            raise typer.Exit(code=1)
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

        discovery_agent = CodeDiscoveryAgent(model_client, tier_config.low, escalation_tier=tier_config.medium)
        file_index = FileIndexService(model_client, tier_config.low)

        # Each milestone gets its own dedicated, long-lived branch — created
        # once and reused across every `haive run` invocation for it, rather
        # than derived from whatever happens to be locally checked out.
        # Every task branches off it and merges into it; only the final
        # "project complete" PR (see the done handling below) ever touches
        # main.
        if project_data is None:
            project_data = pm.get_project(milestone_id)
        project_branch = project_data.project_branch
        if not dry_run:
            vcs.ensure_branch(project_branch, "main")

        if not dry_run:
            resynced = file_index.resync_line_ranges(root)
            if resynced:
                typer.echo(f"Corrected stale line ranges in {len(resynced)} agent.md file(s): {', '.join(resynced)}")

        example_library: ExampleLibrary | None = None
        examples_path = Path(examples)
        if examples_path.exists():
            example_library = ExampleLibrary.load(str(examples_path))
        else:
            typer.echo(f"Note: {examples} not found — running without planning examples.")

        # Build executor components once — stable across every wave in this invocation.
        reviewer_config = registry.get_agent(AgentRole.CODE_REVIEWER_AGENT)
        reviewer_system_prompt = Path(reviewer_config.system_prompt).read_text(encoding="utf-8")
        guidelines_candidates = [Path(root, "GUIDELINES.md"), Path(root, "guidelines.md")]
        guidelines = next(
            (p.read_text(encoding="utf-8") for p in guidelines_candidates if p.exists()), ""
        )
        review_agent = ReviewAgent(
            model_client, reviewer_system_prompt, guidelines, root, models=settings.reviewer_models,
        )
        command_runner = CommandRunner(
            secrets_to_redact=[
                settings.github_token, settings.anthropic_api_key, settings.openai_api_key,
            ]
        )
        execution_verifier = ExecutionVerifier(
            command_runner, root,
            verification_commands=settings.verification_commands,
            skip_roles=settings.verification_skip_roles,
            import_timeout_seconds=settings.verification_import_timeout_seconds,
            command_timeout_seconds=settings.verification_command_timeout_seconds,
            setup_command=settings.verification_setup_command,
            setup_timeout_seconds=settings.verification_setup_timeout_seconds,
            enabled=settings.verification_enabled,
        )
        dependency_approval_gate = DependencyApprovalGate(
            root, enabled=settings.dependency_approval_enabled,
        )
        executor = TaskExecutor(
            model_client, tier_config, review_agent, execution_verifier,
            dependency_approval_gate, root, project_branch,
            auto_merge=settings.auto_merge,
            on_status=typer.echo,
        )

        with run_span(milestone_id):
            for wave_num in range(1, settings.max_waves_per_run + 1):
                if not quiet:
                    typer.secho(f"\n--- Wave {wave_num} ---", bold=True)
                if not quiet:
                    typer.echo(f"Fetching milestone {milestone_id}...")
                tasks = pm.get_tasks(milestone_id)
                if not quiet:
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

                # Reconcile superseded recovery ancestors: once a recovery task
                # completes, every ancestor in its lineage chain (the original
                # task, and any intermediate recovery attempts) is done for —
                # nothing will ever mark them complete themselves, since the
                # completed descendant is the one that actually did the work.
                # Left open, they'd block the "every task complete" done check
                # forever, and any other task that still depends_on one of
                # them would never unblock either. Closing the ancestor and
                # redirecting dependents to the completed descendant fixes
                # both at once.
                tasks_by_id = {t.task_id: t for t in tasks}
                supersede_map: dict[str, str] = {}
                for t in tasks:
                    if t.status != TaskStatus.COMPLETE or not t.recovery_for:
                        continue
                    ancestor_id: str | None = t.recovery_for
                    while ancestor_id is not None and ancestor_id not in supersede_map:
                        ancestor = tasks_by_id.get(ancestor_id)
                        if ancestor is None:
                            break
                        supersede_map[ancestor_id] = t.task_id
                        ancestor_id = ancestor.recovery_for

                reconciled = False
                for ancestor_id, completed_id in supersede_map.items():
                    try:
                        pm.add_comment(
                            ancestor_id,
                            f"**haive:** superseded by #{completed_id}, which completed "
                            "successfully. Closing this issue.",
                        )
                        pm.close_task(ancestor_id)
                        typer.echo(f"  [#{ancestor_id}] superseded by #{completed_id} — closed.")
                        reconciled = True
                    except RuntimeError as exc:
                        typer.echo(f"  [#{ancestor_id}] Could not close superseded task: {exc}")

                if supersede_map:
                    for other in tasks:
                        if other.task_id in supersede_map or not other.depends_on:
                            continue
                        if not any(dep in supersede_map for dep in other.depends_on):
                            continue
                        redirected = [supersede_map.get(dep, dep) for dep in other.depends_on]
                        deduped = list(dict.fromkeys(redirected))
                        try:
                            pm.set_dependency(other.task_id, deduped)
                            typer.echo(
                                f"  [#{other.task_id}] dependency redirected: "
                                f"{other.depends_on} -> {deduped}."
                            )
                            reconciled = True
                        except RuntimeError as exc:
                            typer.echo(f"  [#{other.task_id}] Could not redirect dependency: {exc}")

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
                        return MilestoneRunOutcome.DRY_RUN_PREVIEW
                    if not quiet:
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
                        unstall_task_id=unstall_task_id,
                    )

                    if not quiet:
                        if unstall_task_id is not None:
                            typer.echo(
                                f"Note: task #{unstall_task_id} is exempted from "
                                "max_recovery_depth for this run."
                            )
                        typer.echo("Calling orchestrator...")
                    orchestrator = Orchestrator(
                        model_client, tier_config, settings.max_recovery_depth,
                        settings.max_family_attempts, example_library,
                    )
                    try:
                        output = orchestrator.run_loop(orch_input)
                    except OrchestratorStalledError as e:
                        if e.stalled_task_id is not None:
                            summary = _format_recovery_lineage_summary(
                                e.stalled_task_id, tasks, state, settings.max_recovery_depth
                            )
                            pm.add_comment(e.stalled_task_id, summary)
                        typer.echo(f"\n{e} — waiting on human input.")
                        return MilestoneRunOutcome.STALLED

                    if dry_run:
                        _print_dry_run_output(project_data, output)
                        return MilestoneRunOutcome.DRY_RUN_PREVIEW

                    if output.done:
                        if vcs.branch_has_new_commits("main", project_branch):
                            pr_id = vcs.create_project_pr(
                                project_branch,
                                "main",
                                f"Project complete: {project_data.title}",
                                "All tasks complete — merging project branch to main.",
                            )
                            typer.echo(f"\nProject complete. PR created: {pr_id}")
                            if auto_merge_final_pr:
                                try:
                                    vcs.merge_pr(pr_id)
                                    typer.echo("Final PR merged automatically (milestone checkpoint disabled).")
                                    _close_finished_milestone(pm, milestone_id)
                                    return MilestoneRunOutcome.DONE_MERGED
                                except RuntimeError as exc:
                                    typer.echo(f"Automatic merge of the final PR failed: {exc}")
                                    return MilestoneRunOutcome.DONE_AWAITING_MERGE
                            return MilestoneRunOutcome.DONE_AWAITING_MERGE
                        else:
                            typer.echo(
                                "\nProject complete. All changes were already merged into main "
                                "— nothing further to merge."
                            )
                            _close_finished_milestone(pm, milestone_id)
                            return MilestoneRunOutcome.DONE_MERGED

                    # Create new tasks and resolve "new:N" dependency refs.
                    id_map: dict[str, str] = {}
                    for i, new_task in enumerate(output.new_tasks):
                        created = pm.create_task(milestone_id, new_task)
                        id_map[f"new:{i}"] = created.task_id
                        new_task_objects.append(created)
                        if not quiet:
                            typer.echo(f"  Created task #{created.task_id}: {created.title}")

                    for i, new_task in enumerate(output.new_tasks):
                        if new_task.depends_on:
                            resolved = [id_map.get(dep, dep) for dep in new_task.depends_on]
                            pm.set_dependency(new_task_objects[i].task_id, resolved)
                            new_task_objects[i] = new_task_objects[i].model_copy(
                                update={"depends_on": resolved}
                            )

                # The scheduler needs every known task, not just the pending ones,
                # so a pending task that depends on an already-complete task from
                # an earlier wave can resolve that dependency — TaskScheduler only
                # ever schedules PENDING tasks itself, but it looks up dependency
                # statuses across the whole set handed to it. Passing just the
                # pending subset leaves any such dependency's status permanently
                # unresolvable (not in the map, so never COMPLETE), silently
                # stranding that task forever with no error and no wave-summary
                # count for it. Newly created tasks come from the adapter
                # directly (not re-read from GitHub) because Projects v2 GraphQL
                # does not reflect new items immediately, so they're appended
                # rather than being part of `tasks`.
                all_tasks = tasks + new_task_objects

                wave_complete = 0
                wave_needs_review = 0
                wave_awaiting_merge = 0
                wave_blocked = 0

                def on_task_complete(record: TaskExecutionRecord) -> None:
                    nonlocal wave_complete, wave_needs_review, wave_awaiting_merge
                    passed = record.verdict is not None and record.verdict.passed
                    if passed and record.merged:
                        wave_complete += 1
                        if not quiet:
                            typer.secho(f"  ✓ Task #{record.task_id} — complete", fg="green")
                    elif passed and not record.merged:
                        wave_awaiting_merge += 1
                        if not quiet:
                            typer.secho(f"  ⏳ Task #{record.task_id} — awaiting merge", fg="yellow")
                    else:
                        wave_needs_review += 1
                        if not quiet:
                            typer.secho(f"  ✗ Task #{record.task_id} — needs-human-review", fg="red")

                def executor_factory(task):  # type: ignore[no-untyped-def]
                    return executor.run(
                        task, milestone_id, state,
                        discovery_agent, file_index, registry, pm, vcs, state_store,
                    )

                if not quiet:
                    typer.echo("\nRunning tasks...")
                scheduler = TaskScheduler(max_executors=settings.max_executors)
                scheduler.start(all_tasks, executor_factory, pm, on_complete=on_task_complete)

                final_tasks = pm.get_tasks(milestone_id)
                blocked_tasks = [t for t in final_tasks if t.status == TaskStatus.BLOCKED]
                wave_blocked = len(blocked_tasks)
                for t in blocked_tasks:
                    if not quiet:
                        typer.secho(f"  ⊘ Task #{t.task_id} — blocked", fg="yellow")

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
                f"Re-run '{command_name}' to continue."
            )
            return MilestoneRunOutcome.WAVE_LIMIT_REACHED

    except (RuntimeError, APIError) as e:
        typer.secho(f"Error: {e}", fg="red", err=True)
        raise typer.Exit(code=1)
    except ValidationError as e:
        typer.secho(f"Validation error: {e}", fg="red", err=True)
        raise typer.Exit(code=1)
    except Exception as e:
        # Catches anything not already handled above by a more specific
        # clause — e.g. a FileNotFoundError from somewhere deep in the wave
        # loop (a missing interpreter, a missing file a task touched) that
        # has nothing to do with agents.yaml. A single broad
        # `except FileNotFoundError` here once mislabeled exactly that kind
        # of error as "agents.yaml not found", since agents.yaml's own
        # FileNotFoundError is now caught right at its source above instead.
        typer.secho(f"Error: {type(e).__name__}: {e}", fg="red", err=True)
        raise typer.Exit(code=1)


@app.command()
def run(
    project: str | None = typer.Option(
        None,
        "--project",
        help="GitHub milestone number to run. Overrides GITHUB_MILESTONE_ID in config.",
    ),
    agents: str = typer.Option(
        _DEFAULT_AGENTS_PATH,
        "--agents",
        help="Path to agents.yaml. Defaults to haive's bundled agent registry.",
    ),
    examples: str = typer.Option(
        _DEFAULT_EXAMPLES_PATH,
        "--examples",
        help="Path to orchestrator examples YAML. Defaults to haive's bundled examples; skipped gracefully if not found.",
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
    quiet: bool = typer.Option(
        False,
        "--quiet",
        "-q",
        is_flag=True,
        help="Suppress routine progress output. Outcomes and errors are still printed.",
    ),
    unstall: str | None = typer.Option(
        None,
        "--unstall",
        help=(
            "Task id whose recovery chain hit max_recovery_depth. Authorizes one "
            "recovery attempt beyond the limit for that task's lineage only, after "
            "you've reviewed it (e.g. posted a corrective comment). Every other "
            "lineage is still held to the normal limit."
        ),
    ),
) -> None:
    """Run the haive agent harness for a project milestone.

    Each milestone gets its own dedicated branch (created on first run,
    reused after). The orchestrator plans tasks against the milestone;
    each task is executed with a discover → generate → review loop that
    retries and escalates model tiers on failure, then its PR is created
    and auto-merged into the milestone branch (unless --no-merge). Once
    the orchestrator signals the milestone done, a final PR merges the
    milestone branch into main — this one is never auto-merged, and is
    always left for human review.

    Loops automatically across waves (planning, executing, replanning) up to
    settings.max_waves_per_run, stopping early when the project is done or
    the orchestrator has no further automatic action to take. Re-run to
    continue past the wave limit or to pick up tasks left needing human
    review.
    """
    _preflight_checks()
    milestone_id = _resolve_milestone_id(project)
    _run_milestone(
        milestone_id, agents, examples, dry_run, no_merge, quiet,
        auto_merge_final_pr=False,
        unstall_task_id=unstall,
    )


@app.command("run-all")
def run_all(
    agents: str = typer.Option(
        _DEFAULT_AGENTS_PATH,
        "--agents",
        help="Path to agents.yaml. Defaults to haive's bundled agent registry.",
    ),
    examples: str = typer.Option(
        _DEFAULT_EXAMPLES_PATH,
        "--examples",
        help="Path to orchestrator examples YAML. Defaults to haive's bundled examples; skipped gracefully if not found.",
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
        help="Never auto-merge, even a milestone marked '#Checkpoint: false'. Task PRs still open for review.",
    ),
    quiet: bool = typer.Option(
        False,
        "--quiet",
        "-q",
        is_flag=True,
        help="Suppress routine progress output. Outcomes and errors are still printed.",
    ),
    unstall: str | None = typer.Option(
        None,
        "--unstall",
        help=(
            "Task id whose recovery chain hit max_recovery_depth. Authorizes one "
            "recovery attempt beyond the limit for that task's lineage only, after "
            "you've reviewed it (e.g. posted a corrective comment). Every other "
            "lineage is still held to the normal limit."
        ),
    ),
) -> None:
    """Work through every open milestone in order, without re-invoking per milestone.

    Milestones are ordered by their due_on date — used purely as an
    ordering key, not a literal deadline; set it in GitHub to control
    build order. Milestones without a due_on sort last, by milestone
    number.

    Each milestone defaults to gated: its final PR is created but never
    auto-merged, and this command stops there, reporting that it's waiting
    on a human to merge it. A milestone whose description contains
    '#Checkpoint: false' opts out of that gate — its final PR auto-merges
    and the queue continues immediately to the next milestone.

    This never runs in the background waiting for a merge. Re-invoke it
    once you've merged a gated milestone's PR to continue from there.
    """
    _preflight_checks()

    from haive.adapters.pm.github import GitHubPMAdapter
    from haive.models.config import load_settings

    try:
        settings = load_settings()
    except Exception as e:
        typer.echo(f"Error loading config: {e}", err=True)
        raise typer.Exit(code=1)

    pm = GitHubPMAdapter(settings)
    milestones = pm.list_open_milestones()
    if not milestones:
        typer.echo("No open milestones found.")
        return

    milestones.sort(key=lambda m: (m.due_on is None, m.due_on, m.number))

    processed = 0
    for milestone in milestones:
        if processed >= settings.max_milestones_per_run:
            typer.echo(
                f"\nReached the automatic milestone limit ({settings.max_milestones_per_run}) "
                "for this run. Re-run 'haive run-all' to continue."
            )
            return

        project = pm.get_project(str(milestone.number))
        typer.secho(f"\n=== Milestone #{milestone.number}: {milestone.title} ===", bold=True)

        outcome = _run_milestone(
            str(milestone.number), agents, examples, dry_run, no_merge, quiet,
            auto_merge_final_pr=(not no_merge) and (not project.checkpoint),
            command_name="haive run-all",
            project_data=project,
            unstall_task_id=unstall,
        )
        processed += 1

        if outcome == MilestoneRunOutcome.DONE_MERGED:
            typer.echo(f"Milestone #{milestone.number} complete and merged — continuing to the next milestone.")
            continue

        if outcome == MilestoneRunOutcome.DONE_AWAITING_MERGE:
            typer.echo(
                f"\nMilestone #{milestone.number} is done and waiting on its final PR to be merged "
                "before continuing. Re-run 'haive run-all' once it's merged."
            )
        # WAVE_LIMIT_REACHED, STALLED, and DRY_RUN_PREVIEW already printed
        # their own message inside _run_milestone — nothing more to add here.
        return

    typer.echo(f"\nProcessed all {processed} milestone(s) in the queue.")


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
