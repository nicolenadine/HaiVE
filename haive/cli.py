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
