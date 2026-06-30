from __future__ import annotations

import fnmatch
import os
from pathlib import Path
from typing import Iterator

from haive.discovery.agent_md import AgentMdValidator
from haive.discovery.constants import (
    AGENT_MD_GENERATION_MAX_TOKENS,
    AGENT_MD_MAX_DESCRIPTION_LEN,
    AGENT_MD_MAX_GENERATION_RETRIES,
    AGENT_MD_MAX_LINES,
    AGENT_MD_MAX_SYMBOLS,
    AGENT_MD_MIN_DESCRIPTION_LEN,
    SOURCE_EXTENSIONS,
)
from haive.llm.model_client import ModelClient
from haive.llm.tier import Tier

_GENERATION_SYSTEM_PROMPT = f"""\
You are a code-indexing assistant. Your only task is to write a concise, \
structured agent.md file describing the contents of a source directory.

Format rules (violations cause automatic retry):

## Files  ← required section header, exactly this text

One line per source file or immediate subdirectory:
  filename.ext — one-line description
  subdir/ — one-line description

Rules for ## Files entries:
- Separator is ' — ' (space, em dash U+2014, space). An ASCII hyphen is invalid.
- Description is {AGENT_MD_MIN_DESCRIPTION_LEN}–{AGENT_MD_MAX_DESCRIPTION_LEN} characters, no trailing period.
- List the filename only, not its full path. agent.md itself is never listed.
- Subdirectory entries end with /.

## Key Symbols  ← optional section header, exactly this text

One line per notable symbol (class, function, method, or constant):
  Name (kind) — start-end
where kind is one of: class, function, method, constant
and start-end are 1-based line numbers (both required; start ≤ end).
At most {AGENT_MD_MAX_SYMBOLS} symbol entries.

General rules:
- No prose paragraphs. No headers other than ## Files and ## Key Symbols.
- Total file must not exceed {AGENT_MD_MAX_LINES} lines.
- Start your response directly with '## Files'. No preamble, no explanation.
"""


class AgentMdGenerationError(Exception):
    pass


class FileIndexService:
    def __init__(self, model_client: ModelClient, tier: Tier) -> None:
        self._client = model_client
        self._tier = tier
        self._validator = AgentMdValidator()

    def generate_all(self, root: str) -> None:
        """Generate agent.md for every source directory under root."""
        patterns = self._load_gitignore_patterns(root)
        for dir_path, source_files, subdirs in self._walk_source_dirs(root, patterns):
            self._generate_for_dir(dir_path, source_files, subdirs, root)

    def validate_all(self, root: str) -> dict[str, list[str]]:
        """Return {relative_path: [violations]} for every agent.md found under root.

        Directories with a valid agent.md are omitted from the result.
        Never calls the LLM.
        """
        results: dict[str, list[str]] = {}
        for dirpath, _, filenames in os.walk(root):
            if "agent.md" not in filenames:
                continue
            agent_md_path = os.path.join(dirpath, "agent.md")
            content = Path(agent_md_path).read_text(encoding="utf-8")
            violations = self._validator.validate(content)
            if violations:
                rel = os.path.relpath(agent_md_path, root)
                results[rel] = violations
        return results

    # ── internal ──────────────────────────────────────────────────────────────

    def _walk_source_dirs(
        self, root: str, patterns: list[str]
    ) -> Iterator[tuple[str, list[str], list[str]]]:
        for dirpath, dirnames, filenames in os.walk(root, topdown=True):
            dirnames[:] = sorted(
                d for d in dirnames if not self._should_skip(d, patterns)
            )
            source_files = sorted(f for f in filenames if self._is_source_file(f))
            if source_files:
                yield dirpath, source_files, list(dirnames)

    def _generate_for_dir(
        self,
        dir_path: str,
        source_files: list[str],
        subdirs: list[str],
        root: str,
    ) -> None:
        prompt = self._build_prompt(dir_path, source_files, subdirs, root)
        violations: list[str] = []
        content = ""

        for attempt in range(1, AGENT_MD_MAX_GENERATION_RETRIES + 1):
            response = self._client.call(
                tier=self._tier,
                prompt=prompt,
                system=_GENERATION_SYSTEM_PROMPT,
                max_tokens=AGENT_MD_GENERATION_MAX_TOKENS,
            )
            content = response.content.strip()
            violations = self._validator.validate(content)
            if not violations:
                break
            if attempt < AGENT_MD_MAX_GENERATION_RETRIES:
                prompt = self._build_retry_prompt(prompt, violations)

        if violations:
            rel = os.path.relpath(dir_path, root) if dir_path != root else "."
            raise AgentMdGenerationError(
                f"Failed to generate a valid agent.md for '{rel}' after "
                f"{AGENT_MD_MAX_GENERATION_RETRIES} attempts. "
                f"Last violations: {violations}"
            )

        Path(os.path.join(dir_path, "agent.md")).write_text(
            content + "\n", encoding="utf-8"
        )

    def _build_prompt(
        self,
        dir_path: str,
        source_files: list[str],
        subdirs: list[str],
        root: str,
    ) -> str:
        rel = os.path.relpath(dir_path, root) if dir_path != root else "."
        parts = [
            f"Generate an agent.md for the directory: {rel}",
            "",
            "Source files in this directory:",
        ]
        for f in source_files:
            parts.append(f"  {f}")
        if subdirs:
            parts.append("")
            parts.append("Immediate subdirectories:")
            for d in subdirs:
                parts.append(f"  {d}/")
        parts.append("")
        parts.append(
            "Write the agent.md now. Start directly with '## Files' — no preamble."
        )
        return "\n".join(parts)

    def _build_retry_prompt(self, original_prompt: str, violations: list[str]) -> str:
        violation_lines = "\n".join(f"  - {v}" for v in violations)
        return (
            f"{original_prompt}\n\n"
            f"Your previous response had format violations:\n"
            f"{violation_lines}\n\n"
            f"Fix all violations and try again. Start directly with '## Files'."
        )

    def _load_gitignore_patterns(self, root: str) -> list[str]:
        gitignore_path = os.path.join(root, ".gitignore")
        if not os.path.exists(gitignore_path):
            return []
        patterns: list[str] = []
        with open(gitignore_path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#"):
                    patterns.append(line.rstrip("/"))
        return patterns

    def _should_skip(self, name: str, patterns: list[str]) -> bool:
        if name == ".git":
            return True
        return any(fnmatch.fnmatch(name, p) for p in patterns)

    def _is_source_file(self, name: str) -> bool:
        if name == "agent.md":
            return False
        if name.startswith("."):
            return False
        return os.path.splitext(name)[1].lower() in SOURCE_EXTENSIONS
