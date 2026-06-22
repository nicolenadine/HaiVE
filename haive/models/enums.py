from enum import Enum


class TaskStatus(str, Enum):
    PENDING            = "pending"
    IN_PROGRESS        = "in_progress"
    COMPLETE           = "complete"
    NEEDS_HUMAN_REVIEW = "needs-human-review"
    BLOCKED            = "blocked"
    SKIPPED            = "skipped"


class AgentRole(str, Enum):
    SCAFFOLD_AGENT             = "scaffold_agent"
    IMPLEMENTATION_AGENT       = "implementation_agent"
    CODE_EDITOR_AGENT          = "code_editor_agent"
    REFACTORING_AGENT          = "refactoring_agent"
    API_INTEGRATION_AGENT      = "api_integration_agent"
    DATABASE_AGENT             = "database_agent"
    TEST_GENERATOR_AGENT       = "test_generator_agent"
    CODE_REVIEWER_AGENT        = "code_reviewer_agent"
    SECURITY_REVIEWER_AGENT    = "security_reviewer_agent"
    DOCUMENTATION_WRITER_AGENT = "documentation_writer_agent"


class Complexity(str, Enum):
    LOW    = "low"
    MEDIUM = "medium"
    HIGH   = "high"
