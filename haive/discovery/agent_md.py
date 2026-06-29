import re

from haive.discovery.constants import (
    AGENT_MD_MAX_DESCRIPTION_LEN,
    AGENT_MD_MAX_LINES,
    AGENT_MD_MAX_SYMBOLS,
    AGENT_MD_MIN_DESCRIPTION_LEN,
    AGENT_MD_PROSE_WORD_THRESHOLD,
)

_ALLOWED_SECTIONS = {"## Files", "## Key Symbols"}
_ALLOWED_KINDS = {"class", "function", "method", "constant"}

# path — description  (em dash required; path may include a trailing slash for dirs)
_FILES_ENTRY_RE = re.compile(r"^[^\s].+ — .+$")
# name (kind) — start-end
_SYMBOLS_ENTRY_RE = re.compile(
    r"^(\S+) \((\w+)\) — (\d+)-(\d+)$"
)


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

        if "## Key Symbols" in sections:
            violations.extend(self._check_symbols_section(sections["## Key Symbols"]))

        violations.extend(self._check_prose(lines, sections))

        return violations

    # --- internal helpers ---

    def _parse_sections(self, lines: list[str]) -> dict[str, list[str]]:
        """Split lines into a dict keyed by section header.

        Lines before the first header are ignored. Each value is the list of
        non-blank body lines belonging to that section.
        """
        sections: dict[str, list[str]] = {}
        current_header: str | None = None

        for line in lines:
            if line.startswith("## "):
                current_header = line.rstrip()
                if current_header not in sections:
                    sections[current_header] = []
            elif current_header is not None:
                stripped = line.strip()
                if stripped:
                    sections[current_header].append(stripped)

        return sections

    def _check_files_section(self, entries: list[str]) -> list[str]:
        violations: list[str] = []
        for entry in entries:
            if not _FILES_ENTRY_RE.match(entry):
                violations.append(f"Files entry has wrong format: {entry}")
                continue
            # entry matched — extract the description (everything after ' — ')
            description = entry.split(" — ", 1)[1]
            if len(description) < AGENT_MD_MIN_DESCRIPTION_LEN:
                violations.append(f"Files entry description too short: {entry}")
            elif len(description) > AGENT_MD_MAX_DESCRIPTION_LEN:
                violations.append(f"Files entry description too long: {entry}")
        return violations

    def _check_symbols_section(self, entries: list[str]) -> list[str]:
        violations: list[str] = []
        if len(entries) > AGENT_MD_MAX_SYMBOLS:
            violations.append(f"Key Symbols section exceeds {AGENT_MD_MAX_SYMBOLS}-entry limit")

        for entry in entries:
            m = _SYMBOLS_ENTRY_RE.match(entry)
            if not m:
                violations.append(f"Key Symbols entry has wrong format: {entry}")
                continue

            _, kind, start_str, end_str = m.groups()
            if kind not in _ALLOWED_KINDS:
                violations.append(
                    f"Key Symbols entry has unknown kind '{kind}': {entry}"
                )
            start, end = int(start_str), int(end_str)
            if start > end:
                violations.append(f"Key Symbols entry has invalid line range: {entry}")

        return violations

    def _check_prose(
        self, lines: list[str], sections: dict[str, list[str]]
    ) -> list[str]:
        """Flag lines that look like prose paragraphs.

        A line is prose if it contains >= 10 words AND doesn't match any
        recognized entry pattern AND is not a section header or blank.
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
            if _SYMBOLS_ENTRY_RE.match(line):
                continue
            if len(line.split()) >= AGENT_MD_PROSE_WORD_THRESHOLD:
                violations.append(f"Prose paragraph detected: {line}")
        return violations
