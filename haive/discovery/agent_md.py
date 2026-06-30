import re

from haive.discovery.constants import (
    AGENT_MD_MAX_DESCRIPTION_LEN,
    AGENT_MD_MAX_LINES,
    AGENT_MD_MIN_DESCRIPTION_LEN,
    AGENT_MD_PROSE_WORD_THRESHOLD,
)

_ALLOWED_SECTIONS = {"## Files"}
_ALLOWED_KINDS = {"class", "function", "method", "constant"}

# Unindented file or subdirectory entry: path — description
_FILES_ENTRY_RE = re.compile(r"^[^\s].+ — .+$")
# 2-space indented symbol sub-entry: "  name (kind) — start-end — description"
# Description is optional but encouraged.
_SYMBOL_ENTRY_RE = re.compile(r"^  (\S+) \((\w+)\) — (\d+)-(\d+)(?: — .+)?$")


class AgentMdValidator:
    """Validates an agent.md file against the structural format spec.

    Returns a list of human-readable violation messages; empty means valid.
    All violations are collected before returning (no early exit).
    """

    def validate(self, content: str) -> list[str]:
        lines = content.splitlines()
        violations: list[str] = []

        if len(lines) > AGENT_MD_MAX_LINES:
            violations.append(f"File exceeds {AGENT_MD_MAX_LINES}-line limit ({len(lines)} lines)")

        sections = self._parse_sections(lines)

        if "## Files" not in sections:
            violations.append("Missing required section: ## Files")

        for header in sections:
            if header not in _ALLOWED_SECTIONS:
                violations.append(f"Unknown section header: {header}")

        if "## Files" in sections:
            violations.extend(self._check_files_section(sections["## Files"]))

        violations.extend(self._check_prose(lines))

        return violations

    # --- internal helpers ---

    def _parse_sections(self, lines: list[str]) -> dict[str, list[str]]:
        """Split lines into a dict keyed by section header.

        Leading whitespace is preserved so symbol sub-entries (2-space indent)
        can be distinguished from file entries (no indent) in _check_files_section.
        """
        sections: dict[str, list[str]] = {}
        current_header: str | None = None

        for line in lines:
            if line.startswith("## "):
                current_header = line.rstrip()
                if current_header not in sections:
                    sections[current_header] = []
            elif current_header is not None:
                rstripped = line.rstrip()
                if rstripped.strip():  # skip blank lines
                    sections[current_header].append(rstripped)

        return sections

    def _check_files_section(self, entries: list[str]) -> list[str]:
        violations: list[str] = []

        for entry in entries:
            if entry.startswith("  "):
                # Indented symbol sub-entry
                m = _SYMBOL_ENTRY_RE.match(entry)
                if not m:
                    violations.append(f"Symbol entry has wrong format: {entry.strip()}")
                    continue
                _, kind, start_str, end_str = m.groups()
                if kind not in _ALLOWED_KINDS:
                    violations.append(
                        f"Symbol entry has unknown kind '{kind}': {entry.strip()}"
                    )
                if int(start_str) > int(end_str):
                    violations.append(f"Symbol entry has invalid line range: {entry.strip()}")
            else:
                # File or subdirectory entry
                if not _FILES_ENTRY_RE.match(entry):
                    violations.append(f"Files entry has wrong format: {entry}")
                    continue
                description = entry.split(" — ", 1)[1]
                if len(description) < AGENT_MD_MIN_DESCRIPTION_LEN:
                    violations.append(f"Files entry description too short: {entry}")
                elif len(description) > AGENT_MD_MAX_DESCRIPTION_LEN:
                    violations.append(f"Files entry description too long: {entry}")

        return violations

    def _check_prose(self, lines: list[str]) -> list[str]:
        """Flag lines that look like prose paragraphs.

        A line is prose if it has >= PROSE_WORD_THRESHOLD words and matches
        none of the recognised entry patterns.
        """
        violations: list[str] = []
        for raw_line in lines:
            line = raw_line.strip()
            if not line:
                continue
            if line.startswith("## "):
                continue
            if _FILES_ENTRY_RE.match(line):
                continue
            # Check symbol entry against the raw line to preserve the 2-space indent.
            if _SYMBOL_ENTRY_RE.match(raw_line):
                continue
            if len(line.split()) >= AGENT_MD_PROSE_WORD_THRESHOLD:
                violations.append(f"Prose paragraph detected: {line}")
        return violations
