## Files

agent_registry.py — Registry for loading and managing agent configurations from YAML files
  AgentRegistry (class) — 9-66 — Container for agent configurations indexed by role with YAML loading and validation
  load (method) — 13-50 — Loads agent configurations from YAML file, validates roles and required prompts
  get_agent (method) — 52-56 — Retrieves configuration for a specific agent role
  roles (method) — 58-59 — Returns list of all registered agent roles
  get_orchestrator_summary (method) — 61-66 — Generates summary of all agents' roles, descriptions, and skills
