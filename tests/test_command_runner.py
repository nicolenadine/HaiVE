from __future__ import annotations

from haive.execution.command_runner import CommandRunner


class TestBasicExecution:
    def test_captures_stdout_and_exit_code(self, tmp_path):
        result = CommandRunner().run(["echo", "hello"], cwd=str(tmp_path), timeout_seconds=5)
        assert result.exit_code == 0
        assert result.stdout.strip() == "hello"
        assert result.timed_out is False

    def test_captures_nonzero_exit_code_and_stderr(self, tmp_path):
        result = CommandRunner().run(
            ["python3", "-c", "import sys; sys.stderr.write('boom'); sys.exit(3)"],
            cwd=str(tmp_path), timeout_seconds=5,
        )
        assert result.exit_code == 3
        assert "boom" in result.stderr

    def test_records_cwd_and_command(self, tmp_path):
        result = CommandRunner().run(["echo", "hi"], cwd=str(tmp_path), timeout_seconds=5)
        assert result.cwd == str(tmp_path)
        assert result.command == ["echo", "hi"]


class TestNoShellInterpolation:
    def test_shell_metacharacters_in_an_argument_are_passed_through_literally(self, tmp_path):
        # If this ran through a shell, "; rm -rf /" would be interpreted as a
        # second command instead of a literal echo argument.
        result = CommandRunner().run(
            ["echo", "safe; rm -rf /"], cwd=str(tmp_path), timeout_seconds=5
        )
        assert result.exit_code == 0
        assert "safe; rm -rf /" in result.stdout

    def test_dollar_expansion_is_not_interpreted(self, tmp_path):
        result = CommandRunner().run(
            ["echo", "$(whoami)"], cwd=str(tmp_path), timeout_seconds=5
        )
        assert result.stdout.strip() == "$(whoami)"


class TestTimeout:
    def test_slow_command_is_marked_timed_out_not_crashed(self, tmp_path):
        result = CommandRunner().run(
            ["python3", "-c", "import time; time.sleep(5)"], cwd=str(tmp_path), timeout_seconds=1,
        )
        assert result.timed_out is True
        assert result.exit_code == -1


class TestSanitization:
    def test_secret_values_are_redacted(self, tmp_path):
        runner = CommandRunner(secrets_to_redact=["super-secret-token"])
        result = runner.run(
            ["echo", "token=super-secret-token"], cwd=str(tmp_path), timeout_seconds=5
        )
        assert "super-secret-token" not in result.stdout
        assert "[REDACTED]" in result.stdout

    def test_no_secrets_configured_leaves_output_untouched(self, tmp_path):
        result = CommandRunner().run(["echo", "plain output"], cwd=str(tmp_path), timeout_seconds=5)
        assert result.stdout.strip() == "plain output"

    def test_long_output_is_truncated(self, tmp_path):
        result = CommandRunner().run(
            ["python3", "-c", "print('x' * 5000)"], cwd=str(tmp_path), timeout_seconds=5
        )
        assert len(result.stdout) < 5000
        assert result.stdout.endswith("[truncated]")
