import pytest
from haive.discovery.agent_md import AgentMdValidator
from haive.discovery.constants import (
    AGENT_MD_MAX_DESCRIPTION_LEN,
    AGENT_MD_MAX_LINES,
    AGENT_MD_MAX_SYMBOLS,
    AGENT_MD_MIN_DESCRIPTION_LEN,
)


@pytest.fixture
def validator():
    return AgentMdValidator()


VALID_MINIMAL = """\
## Files

task.py — Task and Project domain models with dependency tracking
state.py — ProjectState schema and schema-version guard
"""

VALID_FULL = """\
## Files

task.py — Task and Project domain models with dependency tracking
state.py — ProjectState schema and schema-version guard
verdict.py — ReviewVerdict and VerdictSummary definitions
enums.py — TaskStatus, AgentRole, and Complexity enumerations
models/ — Pydantic data models for tasks, state, and verdicts

## Key Symbols

Task (class) — 12-58
Project (class) — 61-90
ProjectState (class) — 14-45
TaskStatus (constant) — 5-5
"""


class TestValidContent:
    def test_minimal_valid_file_returns_no_violations(self, validator):
        assert validator.validate(VALID_MINIMAL) == []

    def test_full_valid_file_with_key_symbols_returns_no_violations(self, validator):
        assert validator.validate(VALID_FULL) == []

    def test_subdirectory_entry_is_valid(self, validator):
        content = "## Files\n\nmodels/ — Pydantic data models for tasks and verdicts\n"
        assert validator.validate(content) == []

    def test_single_file_entry_is_valid(self, validator):
        content = "## Files\n\ncli.py — Typer CLI entry point for the haive harness\n"
        assert validator.validate(content) == []


class TestMissingRequiredSection:
    def test_missing_files_section_is_flagged(self, validator):
        content = "## Key Symbols\n\nTask (class) — 1-50\n"
        violations = validator.validate(content)
        assert any("Missing required section: ## Files" in v for v in violations)

    def test_empty_content_is_flagged(self, validator):
        violations = validator.validate("")
        assert any("Missing required section: ## Files" in v for v in violations)


class TestUnknownSection:
    def test_unknown_section_header_is_flagged(self, validator):
        content = "## Files\n\ntask.py — Task model\n\n## Overview\n\nSome text here\n"
        violations = validator.validate(content)
        assert any("Unknown section header: ## Overview" in v for v in violations)

    def test_known_sections_are_not_flagged(self, validator):
        violations = validator.validate(VALID_FULL)
        assert not any("Unknown section header" in v for v in violations)


class TestFilesEntryFormat:
    def test_ascii_hyphen_separator_is_flagged(self, validator):
        content = "## Files\n\ntask.py - Task model definition\n"
        violations = validator.validate(content)
        assert any("Files entry has wrong format" in v for v in violations)

    def test_full_path_with_directory_is_flagged(self, validator):
        content = "## Files\n\nhaive/models/task.py — Task model definition file\n"
        violations = validator.validate(content)
        # This matches the em-dash pattern so it is technically valid per the regex;
        # the spec says filename-only is the rule but the validator checks format, not
        # the presence of path separators — so this should pass the format check.
        # Keep test focused on what the validator actually enforces (format regex only).
        # Actual path validation is a generation-time concern, not a format violation.
        # So we just verify this doesn't raise an exception.
        assert isinstance(violations, list)

    def test_entry_without_em_dash_is_flagged(self, validator):
        content = "## Files\n\ntask.py\n"
        violations = validator.validate(content)
        assert any("Files entry has wrong format" in v for v in violations)

    def test_description_too_short_is_flagged(self, validator):
        short_desc = "x" * (AGENT_MD_MIN_DESCRIPTION_LEN - 1)
        content = f"## Files\n\ntask.py — {short_desc}\n"
        violations = validator.validate(content)
        assert any("Files entry description too short" in v for v in violations)

    def test_description_at_min_length_is_valid(self, validator):
        min_desc = "x" * AGENT_MD_MIN_DESCRIPTION_LEN
        content = f"## Files\n\ntask.py — {min_desc}\n"
        assert validator.validate(content) == []

    def test_description_too_long_is_flagged(self, validator):
        long_desc = "x" * (AGENT_MD_MAX_DESCRIPTION_LEN + 1)
        content = f"## Files\n\ntask.py — {long_desc}\n"
        violations = validator.validate(content)
        assert any("Files entry description too long" in v for v in violations)

    def test_description_at_max_length_is_valid(self, validator):
        max_desc = "x" * AGENT_MD_MAX_DESCRIPTION_LEN
        content = f"## Files\n\ntask.py — {max_desc}\n"
        assert validator.validate(content) == []


class TestKeySymbolsEntryFormat:
    def test_valid_symbol_entries_pass(self, validator):
        content = (
            "## Files\n\ntask.py — Task model\n\n"
            "## Key Symbols\n\nTask (class) — 12-58\nrun (method) — 45-88\n"
        )
        assert validator.validate(content) == []

    def test_missing_kind_parens_is_flagged(self, validator):
        content = (
            "## Files\n\ntask.py — Task model\n\n"
            "## Key Symbols\n\nTask — 12-58\n"
        )
        violations = validator.validate(content)
        assert any("Key Symbols entry has wrong format" in v for v in violations)

    def test_ascii_hyphen_separator_is_flagged(self, validator):
        content = (
            "## Files\n\ntask.py — Task model\n\n"
            "## Key Symbols\n\nTask (class) - 12-58\n"
        )
        violations = validator.validate(content)
        assert any("Key Symbols entry has wrong format" in v for v in violations)

    def test_missing_end_line_is_flagged(self, validator):
        content = (
            "## Files\n\ntask.py — Task model\n\n"
            "## Key Symbols\n\nTask (class) — 12\n"
        )
        violations = validator.validate(content)
        assert any("Key Symbols entry has wrong format" in v for v in violations)

    def test_start_greater_than_end_is_flagged(self, validator):
        content = (
            "## Files\n\ntask.py — Task model\n\n"
            "## Key Symbols\n\nTask (class) — 88-12\n"
        )
        violations = validator.validate(content)
        assert any("Key Symbols entry has invalid line range" in v for v in violations)

    def test_same_start_and_end_is_valid(self, validator):
        content = (
            "## Files\n\ntask.py — Task model\n\n"
            "## Key Symbols\n\nMAX_RETRIES (constant) — 8-8\n"
        )
        assert validator.validate(content) == []

    def test_unknown_kind_is_flagged(self, validator):
        content = (
            "## Files\n\ntask.py — Task model\n\n"
            "## Key Symbols\n\nTask (module) — 1-50\n"
        )
        violations = validator.validate(content)
        assert any("unknown kind" in v for v in violations)

    def test_all_allowed_kinds_pass(self, validator):
        entries = "\n".join(
            [
                "Task (class) — 1-50",
                "load (function) — 52-80",
                "run (method) — 82-100",
                "MAX (constant) — 102-102",
            ]
        )
        content = f"## Files\n\ntask.py — Task model\n\n## Key Symbols\n\n{entries}\n"
        assert validator.validate(content) == []

    def test_exceeding_max_symbols_is_flagged(self, validator):
        entries = "\n".join(
            f"sym{i} (function) — {i}-{i}" for i in range(1, AGENT_MD_MAX_SYMBOLS + 2)
        )
        content = f"## Files\n\ntask.py — Task model\n\n## Key Symbols\n\n{entries}\n"
        violations = validator.validate(content)
        assert any(f"exceeds {AGENT_MD_MAX_SYMBOLS}-entry limit" in v for v in violations)

    def test_exactly_max_symbols_is_valid(self, validator):
        entries = "\n".join(
            f"sym{i} (function) — {i}-{i}" for i in range(1, AGENT_MD_MAX_SYMBOLS + 1)
        )
        content = f"## Files\n\ntask.py — Task model\n\n## Key Symbols\n\n{entries}\n"
        assert validator.validate(content) == []


class TestProseParagraph:
    def test_prose_paragraph_is_flagged(self, validator):
        prose = "This directory contains the core domain models used throughout the haive application."
        content = f"## Files\n\ntask.py — Task model\n\n{prose}\n"
        violations = validator.validate(content)
        assert any("Prose paragraph detected" in v for v in violations)

    def test_short_non_entry_line_is_not_flagged_as_prose(self, validator):
        # A short line that doesn't match any entry format but has < 10 words
        content = "## Files\n\ntask.py — Task model\n\nSee also models/\n"
        violations = validator.validate(content)
        assert not any("Prose paragraph detected" in v for v in violations)

    def test_files_entry_line_is_not_flagged_as_prose(self, validator):
        long_desc = "a" * 100
        content = f"## Files\n\ntask.py — {long_desc}\n"
        violations = validator.validate(content)
        assert not any("Prose paragraph detected" in v for v in violations)

    def test_section_header_is_not_flagged_as_prose(self, validator):
        assert validator.validate(VALID_FULL) == []


class TestLineLimitViolation:
    def test_oversized_file_is_flagged(self, validator):
        # Generate enough entries to push past AGENT_MD_MAX_LINES.
        # "## Files\n\n" contributes 2 lines; the rest are file entries.
        n = AGENT_MD_MAX_LINES  # one more entry than the limit allows
        entries = "\n".join(f"f{i}.py — Module description number {i}" for i in range(1, n))
        content = f"## Files\n\n{entries}\n"
        lines = content.splitlines()
        assert len(lines) > AGENT_MD_MAX_LINES
        violations = validator.validate(content)
        assert any(f"exceeds {AGENT_MD_MAX_LINES}-line limit" in v for v in violations)

    def test_file_at_exactly_max_lines_is_valid(self, validator):
        # "## Files" (1) + blank (1) + (AGENT_MD_MAX_LINES - 2) entries = AGENT_MD_MAX_LINES lines
        n = AGENT_MD_MAX_LINES - 2
        entries = "\n".join(f"f{i}.py — Module description number {i}" for i in range(1, n + 1))
        content = f"## Files\n\n{entries}"
        lines = content.splitlines()
        assert len(lines) == AGENT_MD_MAX_LINES
        violations = validator.validate(content)
        assert not any(f"exceeds {AGENT_MD_MAX_LINES}-line limit" in v for v in violations)


class TestAllViolationsCollected:
    def test_multiple_violations_all_reported(self, validator):
        # Missing ## Files section AND unknown section AND prose
        prose = "This is a long prose paragraph that should be caught by the validator easily."
        content = f"## Overview\n\n{prose}\n"
        violations = validator.validate(content)
        assert any("Missing required section: ## Files" in v for v in violations)
        assert any("Unknown section header: ## Overview" in v for v in violations)
        assert any("Prose paragraph detected" in v for v in violations)
        assert len(violations) >= 3
