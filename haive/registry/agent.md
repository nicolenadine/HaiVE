## Files

__init__.py — Package initialization for agent registry module
agent_registry.py — Registry for loading and managing agent configurations by role
  AgentRegistry (class) — 12-73 — Manages agent configurations indexed by role with YAML loading
  load (method) — 17-53 — Loads and validates agent configurations from a YAML file
  get_agent (method) — 55-59 — Retrieves the configuration for a specific agent role
  roles (method) — 61-62 — Returns list of all registered agent roles
  get_orchestrator_summary (method) — 67-73 — Generates a summary of all agent roles and skills
