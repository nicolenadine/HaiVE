## Files

__init__.py — Package initialization for configuration module
manager.py — ConfigManager for creating, switching, and managing environment configurations
  ConfigManager (class) — 12-154 — Centralized manager for haive configuration files stored in ~/.haive/configs
  active_config_path (method) — 26-35 — Returns path to the currently active configuration file with automatic bootstrapping
  create (method) — 53-63 — Creates a new named configuration file with validation
  use (method) — 66-75 — Switches the active configuration to a named config file
  delete (method) — 78-92 — Deletes a named configuration file (cannot delete active config)
  set_value (method) — 95-115 — Sets or updates a key-value pair in the active configuration
  get_value (method) — 118-127 — Retrieves a configuration value by key from the active config
  edit (method) — 130-135 — Opens the active configuration file in the user's default editor
  show (method) — 138-149 — Returns all configuration values as a dictionary with sensitive values masked
  list_configs (method) — 152-154 — Lists all available configuration names
