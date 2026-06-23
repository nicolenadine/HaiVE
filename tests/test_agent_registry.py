from pathlib import Path

import pytest

from haive.models.enums import AgentRole
from haive.registry.agent_registry import AgentRegistry

ROOT = Path(__file__).resolve().parents[1]
REGISTRY_PATH = ROOT / "agents.yaml"

_VALID_AGENT_YAML = """\
scaffold_agent:
  description: Creates project structure
  skills:
    - create directories
  system_prompt: prompts/scaffold_agent.md
  output_schema: schemas/scaffold_output.json
  max_tokens: 4096
  retry_limit: 2
  prompt_version: "1.0"
"""


# ---------------------------------------------------------------------------
# TestLoad
# ---------------------------------------------------------------------------

class TestLoad:
    def test_loads_all_ten_agents(self):
        registry = AgentRegistry.load(str(REGISTRY_PATH))
        assert len(registry) == 10
        for role in AgentRole:
            cfg = registry.get_agent(role)
            assert cfg.role == role
            assert cfg.description

    def test_missing_required_field_raises(self, tmp_path):
        path = tmp_path / "agents.yaml"
        path.write_text("""\
scaffold_agent:
  skills:
    - do stuff
  system_prompt: prompts/scaffold_agent.md
  output_schema: schemas/scaffold_output.json
  max_tokens: 4096
  retry_limit: 2
  prompt_version: "1.0"
""")
        with pytest.raises(RuntimeError, match="Invalid config for agent 'scaffold_agent'"):
            AgentRegistry.load(str(path))

    def test_unknown_role_raises(self, tmp_path):
        path = tmp_path / "agents.yaml"
        path.write_text("""\
not_a_real_role:
  description: mystery agent
  skills:
    - ???
  system_prompt: prompts/x.md
  output_schema: schemas/x.json
  max_tokens: 1024
  retry_limit: 0
  prompt_version: "1.0"
""")
        with pytest.raises(ValueError, match="Unknown agent role in registry: 'not_a_real_role'"):
            AgentRegistry.load(str(path))

    def test_missing_role_raises(self, tmp_path):
        path = tmp_path / "agents.yaml"
        path.write_text(_VALID_AGENT_YAML)
        with pytest.raises(RuntimeError, match="missing required roles"):
            AgentRegistry.load(str(path))


# ---------------------------------------------------------------------------
# TestOrchestratorSummary
# ---------------------------------------------------------------------------

class TestOrchestratorSummary:
    def test_has_one_line_per_agent(self):
        registry = AgentRegistry.load(str(REGISTRY_PATH))
        summary = registry.get_orchestrator_summary()
        lines = [line for line in summary.strip().splitlines() if line.strip()]
        assert len(lines) == 10
