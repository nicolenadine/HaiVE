from __future__ import annotations

import textwrap

import pytest

from haive.orchestration.example_library import (
    ExampleLibrary,
    OrchestratorExample,
    format_examples_for_prompt,
)
from haive.orchestration.example_selector import ExampleSelector, classify_tags, score_example
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
        tags, _ = classify_tags(text)
        assert "validation_logic" in tags
        assert "existing_code_edit" in tags
        assert "tests_required" in tags

    def test_docs_only_milestone_gets_docs_tag(self):
        tags, _ = classify_tags("Update README and docstrings for the config module")
        assert "docs_required" in tags

    def test_migration_milestone_gets_db_and_security_tags(self):
        tags, _ = classify_tags("Database migration to add index on users table for auth queries")
        assert "database_migration" in tags
        assert "security_sensitive" in tags

    def test_empty_string_returns_empty_set(self):
        tags, excluded = classify_tags("")
        assert tags == set()
        assert excluded == set()

    def test_cli_milestone_gets_cli_tag(self):
        tags, _ = classify_tags("Add a new CLI command for resetting config")
        assert "cli_change" in tags

    def test_case_insensitive(self):
        tags, _ = classify_tags("MODIFY EXISTING CODE")
        assert "existing_code_edit" in tags

    def test_fill_in_todo_bodies_gets_stub_implementation_tag(self):
        text = (
            "Fill in the TODO bodies in the existing ExampleSelector class. "
            "The public method signatures already exist. Add tests for exact tag matches, "
            "partial tag matches, and deterministic tie-breaking."
        )
        tags, _ = classify_tags(text)
        assert "stub_implementation" in tags
        assert "tests_required" in tags
        assert "new_module" not in tags


# ---------------------------------------------------------------------------
# TestClassifyTagsExclusions
# ---------------------------------------------------------------------------

class TestClassifyTagsExclusions:
    def test_do_not_create_new_excludes_new_files_required(self):
        _, excluded = classify_tags("Do not create new files or modules.")
        assert "new_files_required" in excluded

    def test_excluded_tag_removed_from_positive(self):
        # "placeholder" is a positive keyword for new_files_required,
        # but "do not create placeholder files" is an exclusion phrase.
        # Exclusion must win.
        text = "Do not create placeholder files. Update existing loading code."
        positive, excluded = classify_tags(text)
        assert "new_files_required" in excluded
        assert "new_files_required" not in positive

    def test_existing_code_only_excludes_new_files_required(self):
        _, excluded = classify_tags("Existing code only — no scaffold required.")
        assert "new_files_required" in excluded

    def test_modify_existing_alone_does_not_exclude_new_files_required(self):
        # "modify existing" is no longer a bare exclusion phrase — a milestone can
        # legitimately need both new files and edits to existing code.
        _, excluded = classify_tags("Modify existing handler to add stricter validation.")
        assert "new_files_required" not in excluded

    def test_modify_existing_only_excludes_new_files_required(self):
        _, excluded = classify_tags("Modify existing only — no new files required.")
        assert "new_files_required" in excluded

    def test_existing_working_code_excludes_stub_implementation(self):
        _, excluded = classify_tags("Update existing working code to handle edge cases.")
        assert "stub_implementation" in excluded

    def test_no_stubs_excludes_stub_implementation(self):
        _, excluded = classify_tags("Refactor config module. No stubs needed.")
        assert "stub_implementation" in excluded

    def test_exclusion_does_not_affect_unrelated_tags(self):
        # "do not create new files" excludes new_files_required but not validation_logic
        text = "Do not create new files. Add stricter validation and tests."
        positive, excluded = classify_tags(text)
        assert "new_files_required" in excluded
        assert "validation_logic" in positive
        assert "tests_required" in positive

    def test_exclusion_on_never_positive_tag_does_not_error(self):
        # review_artifact_requested exclusion fires but it was never in positive_tags
        text = "No review task needed. Add validation tests."
        positive, excluded = classify_tags(text)
        assert "review_artifact_requested" in excluded
        assert "review_artifact_requested" not in positive


# ---------------------------------------------------------------------------
# TestScoreExample
# ---------------------------------------------------------------------------

class TestScoreExample:
    def test_positive_match_uses_weights(self):
        score = score_example(
            milestone_tags={"existing_code_edit"},
            excluded_tags=set(),
            example_tags={"existing_code_edit"},
        )
        assert score == 2  # _TAG_WEIGHTS["existing_code_edit"] = 2

    def test_unweighted_positive_match_scores_one(self):
        score = score_example(
            milestone_tags={"tests_required"},
            excluded_tags=set(),
            example_tags={"tests_required"},
        )
        assert score == 1  # default weight = 1

    def test_excluded_tag_on_example_applies_penalty(self):
        score = score_example(
            milestone_tags=set(),
            excluded_tags={"new_files_required"},
            example_tags={"new_files_required"},
        )
        assert score <= -5  # _EXCLUDED_TAG_PENALTY["new_files_required"] = 5

    def test_extra_high_impact_tag_applies_penalty(self):
        score = score_example(
            milestone_tags=set(),
            excluded_tags=set(),
            example_tags={"new_files_required"},
        )
        assert score == -2  # _EXTRA_TAG_PENALTY["new_files_required"] = 2

    def test_extra_low_impact_tag_has_no_penalty(self):
        score = score_example(
            milestone_tags={"existing_code_edit"},
            excluded_tags=set(),
            example_tags={"existing_code_edit", "tests_required"},
        )
        # tests_required is extra but has no _EXTRA_TAG_PENALTY entry
        assert score == 2

    def test_combined_penalty_produces_negative_score(self):
        # milestone wants existing_code_edit + validation_logic, excludes new_files_required
        # example has new_files_required (excluded + extra), plus the positive matches
        score = score_example(
            milestone_tags={"existing_code_edit", "validation_logic"},
            excluded_tags={"new_files_required"},
            example_tags={"new_files_required", "existing_code_edit", "validation_logic", "tests_required"},
        )
        # positive: 2 + 2 = 4; excluded: -5; extra (new_files_required): -2 → total: -3
        assert score < 0


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


# ---------------------------------------------------------------------------
# TestMilestone4Regression
# ---------------------------------------------------------------------------

_REGRESSION_YAML = textwrap.dedent("""\
    examples:
      - id: existing_code_validation_change
        pattern_name: Existing-code validation change
        tags:
          - existing_code_edit
          - validation_logic
          - tests_required
        use_when:
          - Modifying existing working code to add or tighten validation
        default_task_graph:
          - agent_role: code_editor_agent
            purpose: Modify existing validation code
            complexity: medium
            depends_on: []
          - agent_role: test_generator_agent
            purpose: Add tests
            complexity: medium
            depends_on: [0]
        common_wrong_outputs:
          - Using implementation_agent for existing code

      - id: missing_files_before_validation
        pattern_name: Missing files before validation
        tags:
          - new_files_required
          - existing_code_edit
          - validation_logic
          - tests_required
        use_when:
          - Files must be created before validation code can run
        default_task_graph:
          - agent_role: scaffold_agent
            purpose: Create missing files
            complexity: low
            depends_on: []
          - agent_role: code_editor_agent
            purpose: Update validation code
            complexity: medium
            depends_on: [0]
          - agent_role: test_generator_agent
            purpose: Add tests
            complexity: medium
            depends_on: [1]
        common_wrong_outputs:
          - Skipping scaffold when files do not exist
""")

_MILESTONE_4_TEXT = (
    "Update existing validation code. "
    "Do not create new files, modules, schemas, or placeholder files."
)

_NEW_MODULE_YAML = textwrap.dedent("""\
    examples:
      - id: new_module_with_stubs
        pattern_name: New module with stubs
        tags:
          - new_module
          - new_files_required
          - stub_implementation
          - tests_required
        use_when:
          - Introducing a new module that does not exist yet
        default_task_graph:
          - agent_role: scaffold_agent
            purpose: Create module skeleton with stubs
            complexity: medium
            depends_on: []
          - agent_role: implementation_agent
            purpose: Fill in stubbed logic
            complexity: medium
            depends_on: [0]
          - agent_role: test_generator_agent
            purpose: Add tests
            complexity: medium
            depends_on: [1]
        common_wrong_outputs:
          - Using code_editor_agent for empty stubs

      - id: existing_code_validation_change
        pattern_name: Existing-code validation change
        tags:
          - existing_code_edit
          - validation_logic
          - tests_required
        use_when:
          - Modifying existing working code to add or tighten validation
        default_task_graph:
          - agent_role: code_editor_agent
            purpose: Modify existing validation code
            complexity: medium
            depends_on: []
          - agent_role: test_generator_agent
            purpose: Add tests
            complexity: medium
            depends_on: [0]
        common_wrong_outputs:
          - Using implementation_agent for existing code
""")

_MILESTONE_5_TEXT = (
    "Introduce a new ExampleSelector module. "
    "The module file does not exist yet. "
    "Implement module skeleton with stub method signatures for selecting examples by tag overlap. "
    "Fill in stub implementation for the selection algorithm. "
    "Add tests for exact tag matches, partial tag matches, and deterministic tie-breaking."
)


class TestMilestone4Regression:
    def _load_regression_lib(self, tmp_path):
        p = tmp_path / "regression.yaml"
        p.write_text(_REGRESSION_YAML)
        return ExampleLibrary.load(str(p))

    def test_new_files_required_is_excluded(self):
        _, excluded = classify_tags(_MILESTONE_4_TEXT)
        assert "new_files_required" in excluded

    def test_top_result_is_existing_code_validation_change(self, tmp_path):
        lib = self._load_regression_lib(tmp_path)
        results = ExampleSelector().select(lib.all(), _MILESTONE_4_TEXT, limit=2)
        assert len(results) >= 1
        assert results[0].id == "existing_code_validation_change"

    def test_missing_files_example_not_in_top_results(self, tmp_path):
        lib = self._load_regression_lib(tmp_path)
        results = ExampleSelector().select(lib.all(), _MILESTONE_4_TEXT, limit=2)
        assert not any(e.id == "missing_files_before_validation" for e in results)


class TestMilestone5Regression:
    def _load_new_module_lib(self, tmp_path):
        p = tmp_path / "new_module.yaml"
        p.write_text(_NEW_MODULE_YAML)
        return ExampleLibrary.load(str(p))

    def test_module_skeleton_fires_stub_implementation_tag(self):
        tags, _ = classify_tags(_MILESTONE_5_TEXT)
        assert "stub_implementation" in tags
        assert "new_module" in tags

    def test_top_result_is_new_module_with_stubs(self, tmp_path):
        lib = self._load_new_module_lib(tmp_path)
        results = ExampleSelector().select(lib.all(), _MILESTONE_5_TEXT, limit=2)
        assert len(results) >= 1
        assert results[0].id == "new_module_with_stubs"

    def test_existing_code_example_does_not_top_new_module_milestone(self, tmp_path):
        lib = self._load_new_module_lib(tmp_path)
        results = ExampleSelector().select(lib.all(), _MILESTONE_5_TEXT, limit=2)
        if len(results) > 1:
            assert results[0].id != "existing_code_validation_change"
