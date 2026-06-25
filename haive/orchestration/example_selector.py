from __future__ import annotations

from haive.orchestration.example_library import OrchestratorExample

_TAG_KEYWORDS: dict[str, list[str]] = {
    "existing_code_edit":        ["modify", "update", "extend", "existing", "loader", "manager"],
    "new_files_required":        ["create missing", "placeholder", "new file", "does not exist", "scaffold", "create stubs", "stub files", "skeleton files"],
    "validation_logic":          ["validat"],
    "tests_required":            ["test", "coverage"],
    "cli_change":                ["cli", "command", "typer", "flag"],
    "database_migration":        ["migration", "schema change", "alter table"],
    "security_sensitive":        ["security", "auth", "secret", "vulnerability", "permission"],
    "review_artifact_requested": ["standalone review", "review artifact", "audit report", "findings report", "security audit"],
    "docs_required":             ["readme", "docs", "documentation", "docstring"],
    "new_module":                ["new module", "new package", "new class", "introduce"],
    "refactor_only":             ["refactor", "rename", "restructure", "clean up", "simplify"],
    "external_api_integration":  ["api integration", "webhook", "third-party", "external service"],
    "stub_implementation":       ["implement stub", "fill stub", "fill in stub", "stubbed logic", "implement module skeleton", "fill module skeleton", "skeleton implementation", "implement skeleton", "unimplemented", "todo body", "todo bodies", "empty method body", "empty function body", "placeholder method", "placeholder function"],
    "config_change":             ["config", "configuration", "settings", "env var"],
}

_TAG_EXCLUSIONS: dict[str, list[str]] = {
    "new_files_required": [
        "do not create new", "no new files", "no scaffold", "do not scaffold",
        "do not add new modules", "do not create new modules",
        "do not create new service files", "do not create service files",
        "do not create new schemas", "do not create schemas",
        "do not create placeholder", "do not create placeholder files",
        "existing-code only", "existing code only", "modify existing only", "update existing only",
        "without creating new files", "without adding new files",
        "do not create files", "do not add files",
        "no new modules", "no new service files", "no new schemas", "no placeholder files",
    ],
    "stub_implementation": [
        "do not use implementation_agent", "not a stub", "not stubbed",
        "no stubs", "existing working code",
    ],
    "review_artifact_requested": [
        "do not add generic review", "executor-level review is automatic",
        "no review task", "no generic review task",
    ],
}

_TAG_WEIGHTS: dict[str, int] = {
    "existing_code_edit":        2,
    "new_files_required":        3,
    "validation_logic":          2,
    "new_module":                2,
    "stub_implementation":       3,
    "database_migration":        4,
    "review_artifact_requested": 4,
    "cli_change":                3,
}

_EXCLUDED_TAG_PENALTY: dict[str, int] = {
    "new_files_required":        5,
    "stub_implementation":       5,
    "database_migration":        5,
    "review_artifact_requested": 6,
    "security_sensitive":        3,
}

_EXTRA_TAG_PENALTY: dict[str, int] = {
    "new_files_required":       2,
    "stub_implementation":      2,
    "database_migration":       2,
    "review_artifact_requested": 3,
    "external_api_integration": 2,
}


def classify_tags(text: str) -> tuple[set[str], set[str]]:
    normalized = text.lower()
    positive_tags = {
        tag for tag, keywords in _TAG_KEYWORDS.items()
        if any(kw in normalized for kw in keywords)
    }
    excluded_tags = {
        tag for tag, phrases in _TAG_EXCLUSIONS.items()
        if any(phrase in normalized for phrase in phrases)
    }
    positive_tags -= excluded_tags
    return positive_tags, excluded_tags


def score_example(
    milestone_tags: set[str],
    excluded_tags: set[str],
    example_tags: set[str],
) -> int:
    score = sum(_TAG_WEIGHTS.get(tag, 1) for tag in milestone_tags & example_tags)
    score -= sum(_EXCLUDED_TAG_PENALTY.get(tag, 4) for tag in example_tags & excluded_tags)
    score -= sum(_EXTRA_TAG_PENALTY.get(tag, 0) for tag in example_tags - milestone_tags)
    return score


class ExampleSelector:
    def select(
        self,
        examples: list[OrchestratorExample],
        milestone_text: str,
        limit: int = 2,
    ) -> list[OrchestratorExample]:
        positive_tags, excluded_tags = classify_tags(milestone_text)
        if not positive_tags:
            return []

        scored = sorted(
            [
                (s, idx, ex)
                for idx, ex in enumerate(examples)
                if (s := score_example(positive_tags, excluded_tags, set(ex.tags))) > 0
            ],
            key=lambda t: (-t[0], t[1]),
        )
        return [ex for _, _, ex in scored[:limit]]
