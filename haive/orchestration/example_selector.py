from __future__ import annotations

from haive.orchestration.example_library import OrchestratorExample

_TAG_KEYWORDS: dict[str, list[str]] = {
    "existing_code_edit":        ["modify", "update", "extend", "existing", "loader", "manager"],
    "new_files_required":        ["create missing", "placeholder", "new file", "does not exist", "scaffold", "stub"],
    "validation_logic":          ["validat"],
    "tests_required":            ["test", "coverage"],
    "cli_change":                ["cli", "command", "typer", "flag"],
    "database_migration":        ["migration", "schema change", "alter table"],
    "security_sensitive":        ["security", "auth", "secret", "vulnerability", "permission"],
    "review_artifact_requested": ["review", "audit", "findings"],
    "docs_required":             ["readme", "docs", "documentation", "docstring"],
    "new_module":                ["new module", "new package", "new class", "introduce"],
    "refactor_only":             ["refactor", "rename", "restructure", "clean up", "simplify"],
    "external_api_integration":  ["api integration", "webhook", "third-party", "external service"],
    "stub_implementation":       ["stub", "skeleton", "placeholder", "interface"],
    "config_change":             ["config", "configuration", "settings", "env var"],
}


def classify_milestone(text: str) -> set[str]:
    lowered = text.lower()
    tags: set[str] = set()
    for tag, keywords in _TAG_KEYWORDS.items():
        if any(kw in lowered for kw in keywords):
            tags.add(tag)
    return tags


class ExampleSelector:
    def select(
        self,
        examples: list[OrchestratorExample],
        milestone_text: str,
        limit: int = 2,
    ) -> list[OrchestratorExample]:
        tags = classify_milestone(milestone_text)
        if not tags:
            return []

        scored = [
            (len(set(ex.tags) & tags), idx, ex)
            for idx, ex in enumerate(examples)
        ]
        scored = [(score, idx, ex) for score, idx, ex in scored if score > 0]
        scored.sort(key=lambda t: (-t[0], t[1]))
        return [ex for _, _, ex in scored[:limit]]
