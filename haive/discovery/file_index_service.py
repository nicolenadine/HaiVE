from __future__ import annotations

import fnmatch
import os
from pathlib import Path
from typing import Iterator

from haive.discovery.agent_md import AgentMdValidator
from haive.discovery.agent_md_generation_agent import AgentMdGenerationAgent
from haive.discovery.constants import (
    AGENT_MD_MAX_GENERATION_RETRIES,
    SOURCE_EXTENSIONS,
)
from haive.llm.model_client import ModelClient
from haive.llm.tier import Tier
from haive.llm.token_counter import TokenCounter
from haive.models.discovery import DiscoveryResult, LoadedSection


class AgentMdGenerationError(Exception):
    pass


class FileIndexService:
    def __init__(self, model_client: ModelClient, tier: Tier) -> None:
        self._agent = AgentMdGenerationAgent(model_client, tier)
        self._validator = AgentMdValidator()

    def generate_all(self, root: str) -> None:
        """Generate agent.md for every source directory under root, leaves first.

        Bottom-up order ensures child agent.md files exist before the parent
        is generated, so the parent agent can read them for accurate subdirectory
        descriptions rather than guessing from directory names alone.
        """
        patterns = self._load_gitignore_patterns(root)
        dirs = list(self._walk_source_dirs(root, patterns))
        for dir_path, source_files, subdirs in reversed(dirs):
            self._generate_for_dir(dir_path, source_files, subdirs, root)

    def load_sections(
        self, result: DiscoveryResult, root: str, token_budget: int
    ) -> list[LoadedSection]:
        """Load source content for each discovered section, most-relevant-first.

        Sections are processed in the order provided by DiscoveryResult (which
        CodeDiscoveryAgent lists most-relevant-first). Loading stops when the
        next section would push the accumulated token count over token_budget;
        all remaining sections are dropped silently.

        Raises FileNotFoundError with a descriptive message if a discovered
        file does not exist on disk.
        """
        loaded: list[LoadedSection] = []
        tokens_used = 0

        for section in result.sections:
            full_path = Path(root) / section.file
            if not full_path.is_file():
                raise FileNotFoundError(
                    f"Discovered file no longer exists: {section.file!r}"
                )

            text = full_path.read_text(encoding="utf-8")

            if section.full or (section.start_line is None or section.end_line is None):
                source = text
            else:
                lines = text.splitlines(keepends=True)
                source = "".join(lines[section.start_line - 1 : section.end_line])

            cost = TokenCounter.estimate(source)
            if tokens_used + cost > token_budget:
                break

            loaded.append(LoadedSection(file=section.file, source=source, reason=section.reason))
            tokens_used += cost

        return loaded

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
        violations: list[str] = []
        content = ""
        prior_violations: list[str] | None = None

        for _ in range(AGENT_MD_MAX_GENERATION_RETRIES):
            content = self._agent.generate(
                dir_path, source_files, subdirs, root, prior_violations
            )
            violations = self._validator.validate(content)
            if not violations:
                break
            prior_violations = violations

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
