## Files

__init__.py — Package initialization for agent registry module
agent_registry.py — AgentRegistry for loading and managing agent configurations from YAML
  AgentRegistry (class) — 12-71 — Registry managing agent role configurations with validation and role lookup
  load (method) — 17-51 — Loads and validates agent configurations from YAML file, ensuring all required roles present
  get_agent (method) — 53-57 — Retrieves agent configuration by role
  roles (method) — 59-60 — Returns list of registered agent roles
  get_orchestrator_summary (method) — 65-71 — Generates summary of all agents and their skills
