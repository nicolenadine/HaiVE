import shutil

import typer

app = typer.Typer(help="Haive — AI agent harness for software development.")

config_app = typer.Typer(help="Manage named configs. (Implemented in Step 2.)")
app.add_typer(config_app, name="config")


def _check_git_on_path() -> None:
    if shutil.which("git") is None:
        typer.echo(
            "Error: 'git' is not found on PATH. Install git and ensure it is on your PATH, then try again.",
            err=True,
        )
        raise typer.Exit(code=1)


def _check_active_config() -> None:
    # Stub: wired to ConfigManager in Step 2.
    pass


def _resolve_project_id(cli_value: str | None) -> str:
    if cli_value is not None:
        return cli_value
    # Stub: reads GITHUB_PROJECT_ID from active config in Step 2.
    config_value: str | None = None
    if config_value is not None:
        return config_value
    typer.echo(
        "Error: No project ID specified. Pass --project <id> or set GITHUB_PROJECT_ID in your active config.",
        err=True,
    )
    raise typer.Exit(code=1)


def _preflight_checks() -> None:
    _check_git_on_path()
    _check_active_config()


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
