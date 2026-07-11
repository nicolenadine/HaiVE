from __future__ import annotations

from haive.execution.command_runner import CommandRunner
from haive.execution.execution_verifier import ExecutionVerifier
from haive.models.enums import AgentRole

_TIMEOUT = 15


def make_verifier(
    root,
    verification_commands: list[str] | None = None,
    skip_roles: list[AgentRole] | None = None,
    enabled: bool = True,
    setup_command: str = "",
) -> ExecutionVerifier:
    return ExecutionVerifier(
        CommandRunner(),
        str(root),
        verification_commands=verification_commands or [],
        skip_roles=skip_roles or [],
        import_timeout_seconds=_TIMEOUT,
        command_timeout_seconds=_TIMEOUT,
        setup_command=setup_command,
        setup_timeout_seconds=_TIMEOUT,
        enabled=enabled,
    )


class TestPathSafety:
    def test_path_escaping_root_is_rejected(self, tmp_path):
        verifier = make_verifier(tmp_path)
        result = verifier.verify(["../../etc/passwd"], AgentRole.CODE_EDITOR_AGENT)
        assert result.passed is False
        assert result.stage == "path_safety"

    def test_path_inside_root_is_not_rejected_on_safety_grounds(self, tmp_path):
        (tmp_path / "ok.py").write_text("x = 1\n")
        verifier = make_verifier(tmp_path)
        result = verifier.verify(["ok.py"], AgentRole.CODE_EDITOR_AGENT)
        assert result.stage != "path_safety"


class TestDependencySync:
    def test_auto_detects_uv_sync_all_extras_when_pyproject_present(self, tmp_path):
        # Regression test: bare "uv sync" only installs the base
        # [project.dependencies] group and actively *uninstalls* anything
        # under [project.optional-dependencies] (e.g. a "dev" group holding
        # pytest) that was already present -- this crashed for real, wiping
        # pytest out of a project's .venv and failing every subsequent
        # auto-detected test-command check with "No module named pytest".
        (tmp_path / "pyproject.toml").write_text("[project]\nname = \"x\"\n")
        verifier = make_verifier(tmp_path)
        assert verifier._setup_command == "uv sync --all-extras"

    def test_no_setup_command_when_no_pyproject(self, tmp_path):
        verifier = make_verifier(tmp_path)
        assert verifier._setup_command == ""

    def test_explicit_setup_command_overrides_auto_detect(self, tmp_path):
        (tmp_path / "pyproject.toml").write_text("[project]\nname = \"x\"\n")
        verifier = make_verifier(tmp_path, setup_command="true")
        assert verifier._setup_command == "true"

    def test_runs_when_venv_missing_and_manifest_present(self, tmp_path):
        (tmp_path / "pyproject.toml").write_text("[project]\nname = \"x\"\n")
        (tmp_path / "ok.py").write_text("x = 1\n")
        verifier = make_verifier(tmp_path, setup_command="false")
        result = verifier.verify(["ok.py"], AgentRole.CODE_EDITOR_AGENT)
        assert result.passed is False
        assert result.stage == "dependency_sync"

    def test_runs_when_manifest_changed_even_if_venv_present(self, tmp_path):
        (tmp_path / "pyproject.toml").write_text("[project]\nname = \"x\"\n")
        venv_bin = tmp_path / ".venv" / "bin"
        venv_bin.mkdir(parents=True)
        (venv_bin / "python").write_text("#!/bin/sh\n")
        (venv_bin / "python").chmod(0o755)
        verifier = make_verifier(tmp_path, setup_command="false")
        result = verifier.verify(["pyproject.toml"], AgentRole.CODE_EDITOR_AGENT)
        assert result.passed is False
        assert result.stage == "dependency_sync"

    def test_skipped_when_manifest_unchanged_and_venv_present(self, tmp_path):
        (tmp_path / "pyproject.toml").write_text("[project]\nname = \"x\"\n")
        venv_bin = tmp_path / ".venv" / "bin"
        venv_bin.mkdir(parents=True)
        (venv_bin / "python").write_text("#!/bin/sh\n")
        (venv_bin / "python").chmod(0o755)
        (tmp_path / "ok.py").write_text("x = 1\n")
        verifier = make_verifier(tmp_path, setup_command="false")
        result = verifier.verify(["ok.py"], AgentRole.CODE_EDITOR_AGENT)
        assert result.passed is True

    def test_passing_setup_command_allows_success(self, tmp_path):
        (tmp_path / "pyproject.toml").write_text("[project]\nname = \"x\"\n")
        (tmp_path / "ok.py").write_text("x = 1\n")
        verifier = make_verifier(tmp_path, setup_command="true")
        result = verifier.verify(["ok.py"], AgentRole.CODE_EDITOR_AGENT)
        assert result.passed is True


class TestSyntaxCheck:
    def test_syntax_error_is_caught(self, tmp_path):
        (tmp_path / "bad.py").write_text("def f(:\n    pass\n")
        verifier = make_verifier(tmp_path)
        result = verifier.verify(["bad.py"], AgentRole.CODE_EDITOR_AGENT)
        assert result.passed is False
        assert result.stage == "syntax"
        assert "bad.py" in result.detail

    def test_valid_syntax_passes_this_stage(self, tmp_path):
        (tmp_path / "good.py").write_text("x = 1\n")
        verifier = make_verifier(tmp_path)
        result = verifier.verify(["good.py"], AgentRole.CODE_EDITOR_AGENT)
        assert result.stage != "syntax"


class TestImportCheck:
    def test_missing_module_import_is_caught(self, tmp_path):
        # The exact class of bug this whole component exists to catch: code
        # that imports a module that doesn't exist at the expected path.
        (tmp_path / "mymod.py").write_text("import this_module_does_not_exist_xyz\n")
        verifier = make_verifier(tmp_path)
        result = verifier.verify(["mymod.py"], AgentRole.CODE_EDITOR_AGENT)
        assert result.passed is False
        assert result.stage == "import"

    def test_importable_module_passes_this_stage(self, tmp_path):
        (tmp_path / "mymod.py").write_text("x = 1\n")
        verifier = make_verifier(tmp_path)
        result = verifier.verify(["mymod.py"], AgentRole.CODE_EDITOR_AGENT)
        assert result.stage != "import"

    def test_package_relative_import_resolves_correctly(self, tmp_path):
        # A file inside a package (pkg/__init__.py present) must be checked
        # as "pkg.mod", not as a bare top-level module.
        (tmp_path / "pkg").mkdir()
        (tmp_path / "pkg" / "__init__.py").write_text("")
        (tmp_path / "pkg" / "mod.py").write_text("x = 1\n")
        verifier = make_verifier(tmp_path)
        result = verifier.verify(["pkg/mod.py", "pkg/__init__.py"], AgentRole.CODE_EDITOR_AGENT)
        assert result.passed is True


class TestConfiguredCommands:
    def test_failing_command_is_caught(self, tmp_path):
        (tmp_path / "ok.py").write_text("x = 1\n")
        verifier = make_verifier(tmp_path, verification_commands=["false"])
        result = verifier.verify(["ok.py"], AgentRole.CODE_EDITOR_AGENT)
        assert result.passed is False
        assert result.stage == "command"

    def test_passing_command_allows_success(self, tmp_path):
        (tmp_path / "ok.py").write_text("x = 1\n")
        verifier = make_verifier(tmp_path, verification_commands=["true"])
        result = verifier.verify(["ok.py"], AgentRole.CODE_EDITOR_AGENT)
        assert result.passed is True

    def test_skip_roles_skips_configured_commands(self, tmp_path):
        (tmp_path / "ok.py").write_text("x = 1\n")
        verifier = make_verifier(
            tmp_path, verification_commands=["false"], skip_roles=[AgentRole.DOCUMENTATION_WRITER_AGENT]
        )
        result = verifier.verify(["ok.py"], AgentRole.DOCUMENTATION_WRITER_AGENT)
        assert result.passed is True

    def test_skip_roles_does_not_skip_syntax_check(self, tmp_path):
        (tmp_path / "bad.py").write_text("def f(:\n")
        verifier = make_verifier(
            tmp_path, verification_commands=["false"], skip_roles=[AgentRole.DOCUMENTATION_WRITER_AGENT]
        )
        result = verifier.verify(["bad.py"], AgentRole.DOCUMENTATION_WRITER_AGENT)
        assert result.passed is False
        assert result.stage == "syntax"

    def test_auto_detects_tests_directory_when_commands_not_configured(self, tmp_path):
        (tmp_path / "ok.py").write_text("x = 1\n")
        (tmp_path / "tests").mkdir()
        (tmp_path / "tests" / "test_fails.py").write_text("def test_x():\n    assert False\n")
        verifier = make_verifier(tmp_path, verification_commands=[])
        result = verifier.verify(["ok.py"], AgentRole.CODE_EDITOR_AGENT)
        assert result.passed is False
        assert result.stage == "command"

    def test_auto_detected_command_uses_resolved_interpreter_not_bare_python(self, tmp_path):
        # Regression test: this used to hardcode the literal string "python",
        # which crashed for real (FileNotFoundError: 'python') on a system
        # with no bare "python" on PATH (e.g. only "python3", or only a
        # project .venv) — the same resolved interpreter the import check
        # already uses (.venv/bin/python if present, else sys.executable)
        # must be used here too, not an unresolved literal.
        (tmp_path / "tests").mkdir()
        verifier = make_verifier(tmp_path, verification_commands=[])
        assert verifier._commands == [f"{verifier._resolve_python()} -m pytest -q"]
        assert verifier._commands[0].split()[0] != "python"

    def test_no_tests_dir_and_no_configured_commands_skips_cleanly(self, tmp_path):
        (tmp_path / "ok.py").write_text("x = 1\n")
        verifier = make_verifier(tmp_path, verification_commands=[])
        result = verifier.verify(["ok.py"], AgentRole.CODE_EDITOR_AGENT)
        assert result.passed is True


class TestOverallOutcomes:
    def test_no_python_files_changed_skips_everything(self, tmp_path):
        verifier = make_verifier(tmp_path, verification_commands=["false"])
        result = verifier.verify(["README.md"], AgentRole.CODE_EDITOR_AGENT)
        assert result.passed is True
        assert result.stage is None

    def test_disabled_verifier_always_passes(self, tmp_path):
        verifier = make_verifier(tmp_path, verification_commands=["false"], enabled=False)
        result = verifier.verify(["../escape"], AgentRole.CODE_EDITOR_AGENT)
        assert result.passed is True

    def test_passing_result_includes_command_results_for_audit(self, tmp_path):
        (tmp_path / "ok.py").write_text("x = 1\n")
        verifier = make_verifier(tmp_path, verification_commands=["true"])
        result = verifier.verify(["ok.py"], AgentRole.CODE_EDITOR_AGENT)
        assert len(result.results) >= 1
