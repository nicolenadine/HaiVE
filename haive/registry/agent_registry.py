from __future__ import annotations

import os

import yaml
from pydantic import ValidationError

from haive.models.config import AgentConfig
from haive.models.enums import AgentRole


class AgentRegistry:
    def __init__(self, agents: dict[AgentRole, AgentConfig]) -> None:
        self._agents = agents

    @classmethod
    def load(cls, path: str) -> "AgentRegistry":
        with open(path) as f:
            raw = yaml.safe_load(f)
        if not isinstance(raw, dict):
            raise RuntimeError(
                f"agents.yaml must be a root-level YAML mapping, got {type(raw).__name__}"
            )
        agents: dict[AgentRole, AgentConfig] = {}
        for key, value in raw.items():
            try:
                role = AgentRole(key)
            except ValueError:
                valid = [r.value for r in AgentRole]
                raise ValueError(
                    f"Unknown agent role in registry: '{key}'. Valid roles: {valid}"
                )
            try:
                agents[role] = AgentConfig(role=role, **value)
            except (ValidationError, TypeError) as e:
                raise RuntimeError(
                    f"Invalid config for agent '{key}': {e}"
                ) from e
        missing = [r.value for r in AgentRole if r not in agents]
        if missing:
            raise RuntimeError(f"Registry is missing required roles: {missing}")

        registry_dir = os.path.dirname(os.path.abspath(path))
        resolved_agents: dict[AgentRole, AgentConfig] = {}
        for role, config in agents.items():
            prompt_path = os.path.join(registry_dir, config.system_prompt)
            if not os.path.isfile(prompt_path):
                raise RuntimeError(
                    f"system_prompt file not found for '{role.value}': {prompt_path!r}"
                )
            resolved_agents[role] = config.model_copy(update={"system_prompt": prompt_path})

        return cls(resolved_agents)

    def get_agent(self, role: AgentRole) -> AgentConfig:
        try:
            return self._agents[role]
        except KeyError:
            raise ValueError(f"No config found for agent role: {role.value!r}")

    def roles(self) -> list[AgentRole]:
        return list(self._agents.keys())

    def __len__(self) -> int:
        return len(self._agents)

    def get_orchestrator_summary(self) -> str:
        lines = []
        for role in AgentRole:
            cfg = self._agents[role]
            skills = ", ".join(cfg.skills)
            lines.append(f"{role.value}: {cfg.description} | Skills: {skills}")
        return "\n".join(lines)
