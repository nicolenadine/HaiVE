## Files

__init__.py — Package initialization for haive configuration management
manager.py — ConfigManager for handling .env-based configuration across named profiles
  ConfigManager (class) — 11-243 — Manages creation, selection, and editing of named environment configurations
  _ensure_dirs (method) — 22-24 — Ensures ~/.haive/configs and ~/.haive/state directories exist
  active_config_path (method) — 26-35 — Returns path to active config file, bootstrapping default if needed
  _bootstrap_default (method) — 37-41 — Creates or resets default config file and marks it active
  _peek_active_name (method) — 43-48 — Returns active config name without side effects
  create (method) — 50-59 — Creates a new named config with validation of config names
  use (method) — 61-70 — Switches to an existing named config
  set_value (method) — 72-92 — Sets a key-value pair in the active config with validation
  get_value (method) — 94-104 — Retrieves a value by key from the active config
  edit (method) — 106-111 — Opens the active config in the system editor for manual editing
  show (method) — 113-126 — Returns all config key-value pairs, masking sensitive values
  list_configs (method) — 128-130 — Lists all available configuration profiles
