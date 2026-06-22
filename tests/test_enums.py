from haive.models.enums import AgentRole, Complexity, TaskStatus


class TestTaskStatus:
    def test_all_values_present(self):
        values = {s.value for s in TaskStatus}
        assert values == {
            "pending",
            "in_progress",
            "complete",
            "needs_human_review",
            "blocked",
            "skipped",
        }

    def test_count(self):
        assert len(TaskStatus) == 6

    def test_serializes_to_string(self):
        assert TaskStatus.IN_PROGRESS == "in_progress"
        assert str(TaskStatus.IN_PROGRESS.value) == "in_progress"

    def test_deserializes_from_string(self):
        assert TaskStatus("in_progress") is TaskStatus.IN_PROGRESS
        assert TaskStatus("needs_human_review") is TaskStatus.NEEDS_HUMAN_REVIEW


class TestAgentRole:
    def test_all_values_present(self):
        values = {r.value for r in AgentRole}
        assert values == {
            "scaffold_agent",
            "implementation_agent",
            "code_editor_agent",
            "refactoring_agent",
            "api_integration_agent",
            "database_agent",
            "test_generator_agent",
            "code_reviewer_agent",
            "security_reviewer_agent",
            "documentation_writer_agent",
        }

    def test_count(self):
        assert len(AgentRole) == 10

    def test_serializes_to_string(self):
        assert AgentRole.SCAFFOLD_AGENT == "scaffold_agent"

    def test_deserializes_from_string(self):
        assert AgentRole("scaffold_agent") is AgentRole.SCAFFOLD_AGENT
        assert AgentRole("documentation_writer_agent") is AgentRole.DOCUMENTATION_WRITER_AGENT


class TestComplexity:
    def test_all_values_present(self):
        values = {c.value for c in Complexity}
        assert values == {"low", "medium", "high"}

    def test_count(self):
        assert len(Complexity) == 3

    def test_serializes_to_string(self):
        assert Complexity.LOW == "low"
        assert Complexity.HIGH == "high"

    def test_deserializes_from_string(self):
        assert Complexity("low") is Complexity.LOW
        assert Complexity("high") is Complexity.HIGH
