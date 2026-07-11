from __future__ import annotations

import subprocess
import time

from haive.models.execution import CommandResult

# A full pytest -q report with several failures easily exceeds a couple
# thousand characters of traceback text -- at 2000 this silently cut a real
# failure report off after only two named failures, hiding the rest of what
# broke from both the retrying agent and this file's own postmortem. Raised
# generously (matching every other too-tight budget found this session)
# rather than re-guessing a "probably enough" number.
_TRUNCATE_CHARS = 8000
_REDACTED = "[REDACTED]"


def _decode(value: bytes | str | None) -> str:
    if value is None:
        return ""
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    return value


class CommandRunner:
    """Runs a fixed argv command as a subprocess, with a timeout, output
    truncation, and secret redaction.

    Commands are always a list[str] run with shell=False — no interpolation,
    no shell injection surface. This class never chooses what to run; it
    only executes whatever list of arguments a caller supplies. Callers are
    expected to source commands from configuration, never from LLM output.
    """

    def __init__(self, secrets_to_redact: list[str] | None = None) -> None:
        self._secrets = [s for s in (secrets_to_redact or []) if s]

    def run(self, command: list[str], cwd: str, timeout_seconds: int) -> CommandResult:
        start = time.monotonic()
        try:
            result = subprocess.run(
                command,
                cwd=cwd,
                capture_output=True,
                text=True,
                timeout=timeout_seconds,
                shell=False,
            )
            return CommandResult(
                command=command,
                cwd=cwd,
                exit_code=result.returncode,
                stdout=self._sanitize(result.stdout),
                stderr=self._sanitize(result.stderr),
                timed_out=False,
                duration_seconds=time.monotonic() - start,
            )
        except subprocess.TimeoutExpired as exc:
            return CommandResult(
                command=command,
                cwd=cwd,
                exit_code=-1,
                stdout=self._sanitize(_decode(exc.stdout)),
                stderr=self._sanitize(_decode(exc.stderr)),
                timed_out=True,
                duration_seconds=time.monotonic() - start,
            )

    def _sanitize(self, text: str) -> str:
        text = text or ""
        for secret in self._secrets:
            text = text.replace(secret, _REDACTED)
        if len(text) > _TRUNCATE_CHARS:
            text = text[:_TRUNCATE_CHARS] + "... [truncated]"
        return text
