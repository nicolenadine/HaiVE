from __future__ import annotations

import json

import pytest

from haive.execution.output_validator import OutputValidationError, OutputValidator
from haive.models.agent_output import CodeEditorOutput, ReviewAgentOutput, ScaffoldAgentOutput
from haive.models.enums import AgentRole


VALID_SCAFFOLD = {
    "files": [{"path": "src/main.py", "content": "print('hello')"}],
    "notes": "",
}

VALID_CODE_EDITOR = {
    "edits": [{"path": "src/client.py", "content": "class Client: pass"}],
    "notes": "",
}

VALID_REVIEW = {
    "passed": True,
    "findings": [],
    "summary": "LGTM",
}

VALID_TEST_GEN = {
    "edits": [{"path": "tests/test_foo.py", "content": "def test_foo(): pass"}],
    "notes": "",
}

VALID_DOC_WRITER = {
    "edits": [{"path": "docs/api.md", "content": "# API"}],
    "notes": "",
}


# ── parsing ───────────────────────────────────────────────────────────────────

class TestJsonExtraction:
    def test_bare_json_object(self):
        raw = json.dumps(VALID_CODE_EDITOR)
        result = OutputValidator().validate(raw, AgentRole.IMPLEMENTATION_AGENT)
        assert isinstance(result, CodeEditorOutput)

    def test_json_in_markdown_fence(self):
        raw = f"Here is my output:\n```json\n{json.dumps(VALID_CODE_EDITOR)}\n```"
        result = OutputValidator().validate(raw, AgentRole.IMPLEMENTATION_AGENT)
        assert isinstance(result, CodeEditorOutput)

    def test_json_in_unlabelled_fence(self):
        raw = f"```\n{json.dumps(VALID_CODE_EDITOR)}\n```"
        result = OutputValidator().validate(raw, AgentRole.IMPLEMENTATION_AGENT)
        assert isinstance(result, CodeEditorOutput)

    def test_json_embedded_in_prose(self):
        raw = f"Sure! Here's the result: {json.dumps(VALID_CODE_EDITOR)} Hope that helps."
        result = OutputValidator().validate(raw, AgentRole.CODE_EDITOR_AGENT)
        assert isinstance(result, CodeEditorOutput)

    def test_unparseable_raises(self):
        with pytest.raises(OutputValidationError) as exc_info:
            OutputValidator().validate("not json at all", AgentRole.IMPLEMENTATION_AGENT)
        assert exc_info.value.role == AgentRole.IMPLEMENTATION_AGENT
        assert "not json at all" in exc_info.value.raw

    def test_incidental_brace_in_prose_before_real_json_is_skipped(self):
        # Regression test: a model reasoning out loud can quote code containing
        # braces (an f-string like `{wave_num}`) before its real JSON answer.
        # That incidental span brace-balances but isn't valid JSON, and must
        # not be mistaken for the answer.
        raw = (
            "Let me identify what to change first.\n"
            '1. `typer.secho(f"\\n--- Wave {wave_num} ---")`\n\n'
            f"{json.dumps(VALID_CODE_EDITOR)}"
        )
        result = OutputValidator().validate(raw, AgentRole.CODE_EDITOR_AGENT)
        assert isinstance(result, CodeEditorOutput)

    def test_multiple_incidental_braces_before_real_json(self):
        raw = (
            "Consider `{unquoted: key}` and `{another bad one}` as examples, then:\n\n"
            f"{json.dumps(VALID_CODE_EDITOR)}"
        )
        result = OutputValidator().validate(raw, AgentRole.CODE_EDITOR_AGENT)
        assert isinstance(result, CodeEditorOutput)

    def test_unbalanced_brace_inside_generated_code_content_does_not_break_extraction(self):
        # Regression test: a naive character-counting brace scanner doesn't
        # know it's inside a JSON string value, so a single stray '}' in
        # generated source code (an f-string fragment, a dict literal, a
        # comment) can desynchronize the depth count and cut the JSON span
        # short before the real closing brace — even though the JSON itself
        # is well-formed. This is what actually broke test_generator_agent
        # output in production: generated test code containing braces.
        payload = {
            "edits": [{
                "path": "tests/test_cli.py",
                "content": 'def test_x():\n    return f"{value}"\n',
            }],
            "notes": "",
        }
        raw = json.dumps(payload)
        result = OutputValidator().validate(raw, AgentRole.CODE_EDITOR_AGENT)
        assert isinstance(result, CodeEditorOutput)
        assert result.edits[0].content == payload["edits"][0]["content"]

    def test_stray_unmatched_closing_brace_inside_string_value(self):
        # A lone '}' inside a string, with no matching '{' anywhere nearby in
        # that string, is the sharpest version of the bug: it can bring a
        # naive counter's running depth to zero prematurely.
        raw = r'{"edits": [{"path": "a.py", "content": "x = 1}\n"}], "notes": ""}'
        result = OutputValidator().validate(raw, AgentRole.CODE_EDITOR_AGENT)
        assert isinstance(result, CodeEditorOutput)
        assert result.edits[0].content == "x = 1}\n"

    def test_escaped_backslash_before_quote_does_not_confuse_string_tracking(self):
        # A literal backslash immediately preceding a quote (e.g. a Windows
        # path) must not be misread as escaping that quote.
        payload = {
            "edits": [{"path": "a.py", "content": 'path = "C:\\\\temp"\n'}],
            "notes": "",
        }
        raw = json.dumps(payload)
        result = OutputValidator().validate(raw, AgentRole.CODE_EDITOR_AGENT)
        assert isinstance(result, CodeEditorOutput)
        assert result.edits[0].content == payload["edits"][0]["content"]


# ── schema validation ─────────────────────────────────────────────────────────

class TestSchemaValidation:
    def test_extra_fields_rejected(self):
        raw = json.dumps({**VALID_CODE_EDITOR, "unexpected_field": "oops"})
        with pytest.raises(OutputValidationError):
            OutputValidator().validate(raw, AgentRole.IMPLEMENTATION_AGENT)

    def test_missing_required_field_raises(self):
        raw = json.dumps({"notes": "missing edits field"})
        with pytest.raises(OutputValidationError):
            OutputValidator().validate(raw, AgentRole.CODE_EDITOR_AGENT)

    def test_wrong_type_raises(self):
        raw = json.dumps({"edits": "should be a list", "notes": ""})
        with pytest.raises(OutputValidationError):
            OutputValidator().validate(raw, AgentRole.IMPLEMENTATION_AGENT)

    def test_empty_edits_list_raises(self):
        # A submission with zero edits can never satisfy a code-editing task —
        # reject it here rather than let it silently pass review as a no-op.
        raw = json.dumps({"edits": [], "notes": "nothing to change"})
        with pytest.raises(OutputValidationError):
            OutputValidator().validate(raw, AgentRole.CODE_EDITOR_AGENT)

    def test_empty_files_list_raises(self):
        raw = json.dumps({"files": [], "notes": ""})
        with pytest.raises(OutputValidationError):
            OutputValidator().validate(raw, AgentRole.SCAFFOLD_AGENT)


# ── all ten roles ─────────────────────────────────────────────────────────────

class TestAllRoles:
    @pytest.mark.parametrize("role", [
        AgentRole.IMPLEMENTATION_AGENT,
        AgentRole.CODE_EDITOR_AGENT,
        AgentRole.REFACTORING_AGENT,
        AgentRole.API_INTEGRATION_AGENT,
        AgentRole.DATABASE_AGENT,
    ])
    def test_code_editor_roles(self, role):
        result = OutputValidator().validate(json.dumps(VALID_CODE_EDITOR), role)
        assert hasattr(result, "edits")

    def test_scaffold_agent(self):
        result = OutputValidator().validate(json.dumps(VALID_SCAFFOLD), AgentRole.SCAFFOLD_AGENT)
        assert isinstance(result, ScaffoldAgentOutput)
        assert result.files[0].path == "src/main.py"

    def test_test_generator_agent(self):
        result = OutputValidator().validate(json.dumps(VALID_TEST_GEN), AgentRole.TEST_GENERATOR_AGENT)
        assert hasattr(result, "edits")

    def test_documentation_writer_agent(self):
        result = OutputValidator().validate(json.dumps(VALID_DOC_WRITER), AgentRole.DOCUMENTATION_WRITER_AGENT)
        assert hasattr(result, "edits")

    @pytest.mark.parametrize("role", [
        AgentRole.CODE_REVIEWER_AGENT,
        AgentRole.SECURITY_REVIEWER_AGENT,
    ])
    def test_reviewer_roles(self, role):
        result = OutputValidator().validate(json.dumps(VALID_REVIEW), role)
        assert isinstance(result, ReviewAgentOutput)
        assert result.passed is True


# ── error detail ──────────────────────────────────────────────────────────────

class TestErrorDetail:
    def test_error_contains_role(self):
        with pytest.raises(OutputValidationError) as exc_info:
            OutputValidator().validate("{}", AgentRole.SCAFFOLD_AGENT)
        assert "scaffold_agent" in str(exc_info.value)

    def test_error_contains_raw_string(self):
        raw = '{"bad": true}'
        with pytest.raises(OutputValidationError) as exc_info:
            OutputValidator().validate(raw, AgentRole.IMPLEMENTATION_AGENT)
        assert raw in exc_info.value.raw


# ── schema files ──────────────────────────────────────────────────────────────

class TestSchemaFiles:
    def test_all_schema_files_exist(self):
        import json
        from pathlib import Path
        schemas_dir = Path(__file__).parent.parent / "haive" / "resources" / "schemas"
        for role in AgentRole:
            schema_path = schemas_dir / f"{role.value}.json"
            assert schema_path.exists(), f"Missing schema file: {schema_path.name}"
            data = json.loads(schema_path.read_text())
            assert "properties" in data or "$defs" in data
