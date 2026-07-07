## Files

__init__.py — Package initialization for configuration module
manager.py — ConfigManager for creating, switching, and managing environment configurations
  ConfigManager (class) — 12-137 — Centralized manager for haive configuration files stored in ~/.haive/configs
  active_config_path (method) — 26-35 — Returns path to the currently active configuration file with automatic bootstrapping
  create (method) — 53-63 — Creates a new named configuration file with validation
  use (method) — 66-75 — Switches the active configuration to a named config file
  set_value (method) — 78-98 — Sets or updates a key-value pair in the active configuration
  get_value (method) — 101-110 — Retrieves a configuration value by key from the active config
  show (method) — 121-132 — Returns all configuration values as a dictionary with sensitive values masked
  list_configs (method) — 135-137 — Lists all available configuration names
