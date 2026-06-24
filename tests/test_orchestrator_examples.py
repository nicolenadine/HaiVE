from __future__ import annotations

import textwrap

import pytest

from haive.orchestration.example_library import (
    ExampleLibrary,
    OrchestratorExample,
    format_examples_for_prompt,
)
from haive.orchestration.example_selector import ExampleSelector, classify_milestone
from haive.orchestration.prompts import build_orchestrator_system_prompt


# ---------------------------------------------------------------------------
# YAML fixtures
# ---------------------------------------------------------------------------

_VALID_YAML = textwrap.dedent("""\
    examples:
      - id: test_pattern_a
        pattern_name: Pattern A
        tags:
          - existing_code_edit
          - validation_logic
        use_when:
          - Modifying existing validation code
        do_not_use_when:
          - Files do not exist yet
        default_task_graph:
          - agent_role: code_editor_agent
            purpose: Modify existing validation
            complexity: medium
            depends_on: []
          - agent_role: test_generator_agent
            purpose: Add tests
            complexity: medium
            depends_on: [0]
        common_wrong_outputs:
          - Using implementation_agent for existing code
        mini_example:
          milestone: Add stricter validation to existing handler
          expected_tasks:
            - title: Update validation logic
              agent_role: code_editor_agent
              complexity: medium
              depends_on: []
            - title: Add validation tests
              agent_role: test_generator_agent
              complexity: medium
              depends_on: [0]

      - id: test_pattern_b
        pattern_name: Pattern B
        tags:
          - new_files_required
          - new_module
        use_when:
          - Creating a new module from scratch
        default_task_graph:
          - agent_role: scaffold_agent
            purpose: Create module skeleton
            complexity: low
            depends_on: []
          - agent_role: implementation_agent
            purpose: Fill in logic
            complexity: medium
            depends_on: [0]
        common_wrong_outputs:
          - Using code_editor_agent before files exist
""")

_DUPLICATE_ID_YAML = textwrap.dedent("""\
    examples:
      - id: dupe
        pattern_name: First
        tags: [existing_code_edit]
        use_when: [reason]
        default_task_graph:
          - agent_role: code_editor_agent
            purpose: do thing
            complexity: medium
            depends_on: []
        common_wrong_outputs: []
      - id: dupe
        pattern_name: Second
        tags: [existing_code_edit]
        use_when: [reason]
        default_task_graph:
          - agent_role: code_editor_agent
            purpose: do thing
            complexity: medium
            depends_on: []
        common_wrong_outputs: []
""")

_UNKNOWN_ROLE_YAML = textwrap.dedent("""\
    examples:
      - id: bad_role
        pattern_name: Bad
        tags: [existing_code_edit]
        use_when: [reason]
        default_task_graph:
          - agent_role: imaginary_agent
            purpose: do something
            complexity: medium
            depends_on: []
""")

_UNKNOWN_COMPLEXITY_YAML = textwrap.dedent("""\
    examples:
      - id: bad_complexity
        pattern_name: Bad
        tags: [existing_code_edit]
        use_when: [reason]
        default_task_graph:
          - agent_role: code_editor_agent
            purpose: do something
            complexity: extreme
            depends_on: []
""")

_MISSING_FIELD_YAML = textwrap.dedent("""\
    examples:
      - id: missing_field
        tags: [existing_code_edit]
        use_when: [reason]
        default_task_graph:
          - agent_role: code_editor_agent
            purpose: do something
            complexity: medium
            depends_on: []
""")

_UNKNOWN_TAG_YAML = textwrap.dedent("""\
    examples:
      - id: bad_tag
        pattern_name: Bad Tag
        tags: [existing_code_edti]
        use_when: [reason]
        default_task_graph:
          - agent_role: code_editor_agent
            purpose: do something
            complexity: medium
            depends_on: []
""")


# ---------------------------------------------------------------------------
# TestExampleLibraryLoading
# ---------------------------------------------------------------------------

class TestExampleLibraryLoading:
    def test_valid_library_loads(self, tmp_path):
        p = tmp_path / "examples.yaml"
        p.write_text(_VALID_YAML)
        lib = ExampleLibrary.load(str(p))
        assert len(lib) == 2
        assert lib.get("test_pattern_a").pattern_name == "Pattern A"

    def test_duplicate_ids_raise(self, tmp_path):
        p = tmp_path / "examples.yaml"
        p.write_text(_DUPLICATE_ID_YAML)
        with pytest.raises(RuntimeError, match="[Dd]uplicate"):
            ExampleLibrary.load(str(p))

    def test_unknown_agent_role_raises(self, tmp_path):
        p = tmp_path / "examples.yaml"
        p.write_text(_UNKNOWN_ROLE_YAML)
        with pytest.raises(RuntimeError):
            ExampleLibrary.load(str(p))

    def test_unknown_complexity_raises(self, tmp_path):
        p = tmp_path / "examples.yaml"
        p.write_text(_UNKNOWN_COMPLEXITY_YAML)
        with pytest.raises(RuntimeError):
            ExampleLibrary.load(str(p))

    def test_missing_required_field_raises(self, tmp_path):
        p = tmp_path / "examples.yaml"
        p.write_text(_MISSING_FIELD_YAML)
        with pytest.raises(RuntimeError):
            ExampleLibrary.load(str(p))

    def test_get_unknown_id_raises(self, tmp_path):
        p = tmp_path / "examples.yaml"
        p.write_text(_VALID_YAML)
        lib = ExampleLibrary.load(str(p))
        with pytest.raises(ValueError, match="[Nn]o example"):
            lib.get("nonexistent")

    def test_unknown_tag_raises(self, tmp_path):
        p = tmp_path / "examples.yaml"
        p.write_text(_UNKNOWN_TAG_YAML)
        with pytest.raises(RuntimeError, match="[Uu]nknown tag"):
            ExampleLibrary.load(str(p))


# ---------------------------------------------------------------------------
# TestMilestoneClassifier
# ---------------------------------------------------------------------------

class TestMilestoneClassifier:
    def test_validation_milestone_gets_expected_tags(self):
        text = "Modify existing handler to add email validation with tests"
        tags = classify_milestone(text)
        assert "validation_logic" in tags
        assert "existing_code_edit" in tags
        assert "tests_required" in tags

    def test_docs_only_milestone_gets_docs_tag(self):
        tags = classify_milestone("Update README and docstrings for the config module")
        assert "docs_required" in tags

    def test_migration_milestone_gets_db_and_security_tags(self):
        tags = classify_milestone("Database migration to add index on users table for auth queries")
        assert "database_migration" in tags
        assert "security_sensitive" in tags

    def test_empty_string_returns_empty_set(self):
        assert classify_milestone("") == set()

    def test_cli_milestone_gets_cli_tag(self):
        tags = classify_milestone("Add a new CLI command for resetting config")
        assert "cli_change" in tags

    def test_case_insensitive(self):
        tags = classify_milestone("MODIFY EXISTING CODE")
        assert "existing_code_edit" in tags

    def test_fill_in_todo_bodies_gets_stub_implementation_tag(self):
        text = (
            "Fill in the TODO bodies in the existing ExampleSelector class. "
            "The public method signatures already exist. Add tests for exact tag matches, "
            "partial tag matches, and deterministic tie-breaking."
        )
        tags = classify_milestone(text)
        assert "stub_implementation" in tags
        assert "tests_required" in tags
        assert "new_module" not in tags


# ---------------------------------------------------------------------------
# TestExampleSelector
# ---------------------------------------------------------------------------

def _load_lib(tmp_path):
    p = tmp_path / "examples.yaml"
    p.write_text(_VALID_YAML)
    return ExampleLibrary.load(str(p))


class TestExampleSelector:
    def test_selects_example_with_matching_tags(self, tmp_path):
        lib = _load_lib(tmp_path)
        sel = ExampleSelector()
        results = sel.select(lib.all(), "Modify existing validation logic", limit=2)
        assert any(e.id == "test_pattern_a" for e in results)

    def test_no_matching_tags_returns_empty(self, tmp_path):
        lib = _load_lib(tmp_path)
        sel = ExampleSelector()
        results = sel.select(lib.all(), "")
        assert results == []

    def test_limit_respected(self, tmp_path):
        lib = _load_lib(tmp_path)
        sel = ExampleSelector()
        results = sel.select(lib.all(), "modify existing new module stub test", limit=1)
        assert len(results) <= 1

    def test_tie_returns_yaml_order(self, tmp_path):
        lib = _load_lib(tmp_path)
        sel = ExampleSelector()
        # Both examples have 1 matching tag each with different tags in text
        results = sel.select(lib.all(), "modify existing new module", limit=2)
        ids = [e.id for e in results]
        # test_pattern_a comes first in YAML — if both score 1, it should come first
        if "test_pattern_a" in ids and "test_pattern_b" in ids:
            assert ids.index("test_pattern_a") < ids.index("test_pattern_b")

    def test_higher_scoring_example_ranked_first(self, tmp_path):
        lib = _load_lib(tmp_path)
        sel = ExampleSelector()
        # "existing code validation modify" hits existing_code_edit + validation_logic → test_pattern_a scores 2
        # "new module" hits new_files_required + new_module → test_pattern_b scores 2
        # "existing code validation" only → test_pattern_a should rank first
        results = sel.select(lib.all(), "modify existing validation logic", limit=2)
        assert results[0].id == "test_pattern_a"


# ---------------------------------------------------------------------------
# TestPromptFormatter
# ---------------------------------------------------------------------------

def _make_example(tmp_path) -> OrchestratorExample:
    p = tmp_path / "examples.yaml"
    p.write_text(_VALID_YAML)
    return ExampleLibrary.load(str(p)).get("test_pattern_a")


class TestPromptFormatter:
    def test_contains_pattern_name(self, tmp_path):
        ex = _make_example(tmp_path)
        output = format_examples_for_prompt([ex])
        assert "Pattern A" in output

    def test_contains_agent_role_values(self, tmp_path):
        ex = _make_example(tmp_path)
        output = format_examples_for_prompt([ex])
        assert "code_editor_agent" in output
        assert "test_generator_agent" in output

    def test_contains_dependency_description(self, tmp_path):
        ex = _make_example(tmp_path)
        output = format_examples_for_prompt([ex])
        assert "step 1" in output

    def test_contains_common_wrong_outputs(self, tmp_path):
        ex = _make_example(tmp_path)
        output = format_examples_for_prompt([ex])
        assert "implementation_agent" in output

    def test_does_not_contain_raw_yaml_keys(self, tmp_path):
        ex = _make_example(tmp_path)
        output = format_examples_for_prompt([ex])
        assert "agent_role:" not in output
        assert "use_when:" not in output
        assert "default_task_graph:" not in output

    def test_empty_list_returns_empty_string(self):
        assert format_examples_for_prompt([]) == ""


# ---------------------------------------------------------------------------
# TestOrchestratorPromptIntegration
# ---------------------------------------------------------------------------

class TestOrchestratorPromptIntegration:
    def test_examples_included_when_provided(self):
        prompt = build_orchestrator_system_prompt(3, "some example text")
        assert "some example text" in prompt

    def test_no_examples_section_when_none(self):
        prompt = build_orchestrator_system_prompt(3, None)
        assert "Relevant planning examples" not in prompt

    def test_prompt_still_valid_without_examples(self):
        prompt = build_orchestrator_system_prompt(3)
        assert "Recovery rules" in prompt
        assert "Done condition" in prompt

    def test_orchestrator_output_schema_unchanged(self):
        from haive.models.orchestrator import OrchestratorOutput
        fields = set(OrchestratorOutput.model_fields.keys())
        assert fields == {"new_tasks", "done"}
