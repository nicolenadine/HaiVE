import shutil

import typer

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
    except FileExistsError as e:
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
    ConfigManager.set_value(key, value)
    typer.echo(f"Set {key} in active config.")


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
    active = ConfigManager.active_name()
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


def _resolve_project_id(cli_value: str | None) -> str:
    if cli_value is not None:
        return cli_value
    config_value = ConfigManager.get_value("GITHUB_PROJECT_ID")
    if config_value:
        return config_value
    typer.echo(
        "Error: No project ID specified. Pass --project <id> or set GITHUB_PROJECT_ID in your active config.",
        err=True,
    )
    raise typer.Exit(code=1)


def _preflight_checks() -> None:
    _check_git_on_path()
    _check_active_config()


# ── Run command ───────────────────────────────────────────────────────────────

@app.command()
def run(
    project: str | None = typer.Option(
        None,
        "--project",
        help="GitHub Project ID to run. Overrides GITHUB_PROJECT_ID in config.",
    ),
) -> None:
    """Run the haive agent harness for a project."""
    _preflight_checks()
    project_id = _resolve_project_id(project)
    typer.echo(f"haive run --project {project_id}: not implemented yet.")
    raise typer.Exit(code=0)


if __name__ == "__main__":
    app()
