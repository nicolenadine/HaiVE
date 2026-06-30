from __future__ import annotations

KNOWN_TAGS: frozenset[str] = frozenset({
    "existing_code_edit",
    "new_files_required",
    "validation_logic",
    "tests_required",
    "cli_change",
    "database_migration",
    "security_sensitive",
    "review_artifact_requested",
    "docs_required",
    "new_module",
    "refactor_only",
    "external_api_integration",
    "stub_implementation",
    "config_change",
})
