import os
import re
import shlex
import subprocess
from pathlib import Path


_VALID_NAME = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9_-]*$")
_VALID_KEY = re.compile(r"^[A-Z][A-Z0-9_]*$")


class ConfigManager:
    _HAIVE_DIR = Path.home() / ".haive"
    _CONFIGS_DIR = _HAIVE_DIR / "configs"
    _ACTIVE_FILE = _HAIVE_DIR / "active"
    _STATE_DIR = _HAIVE_DIR / "state"

    _SENSITIVE = re.compile(r"TOKEN|KEY|SECRET|PASSWORD", re.IGNORECASE)

    @classmethod
    def _ensure_dirs(cls) -> None:
        cls._CONFIGS_DIR.mkdir(parents=True, exist_ok=True)
        cls._STATE_DIR.mkdir(parents=True, exist_ok=True)

    @classmethod
    def active_config_path(cls) -> str:
        cls._ensure_dirs()
        if not cls._ACTIVE_FILE.exists() or not cls._ACTIVE_FILE.read_text().strip():
            cls._bootstrap_default()
        name = cls._ACTIVE_FILE.read_text().strip()
        path = cls._CONFIGS_DIR / f"{name}.env"
        if not path.exists():
            cls._bootstrap_default()
            path = cls._CONFIGS_DIR / "default.env"
        return str(path)

    @classmethod
    def _bootstrap_default(cls) -> None:
        default = cls._CONFIGS_DIR / "default.env"
        if not default.exists():
            default.touch()
        cls._ACTIVE_FILE.write_text("default")

    @classmethod
    def _peek_active_name(cls) -> str | None:
        """Return the active config name without any bootstrapping side effects."""
        if not cls._ACTIVE_FILE.exists():
            return None
        name = cls._ACTIVE_FILE.read_text().strip()
        return name or None

    @classmethod
    def create(cls, name: str) -> None:
        if not _VALID_NAME.match(name):
            raise ValueError(
                f"Invalid config name '{name}'. "
                "Use letters, digits, hyphens, and underscores only (must start with a letter or digit)."
            )
        cls._ensure_dirs()
        path = cls._CONFIGS_DIR / f"{name}.env"
        if path.exists():
            raise FileExistsError(f"Config '{name}' already exists: {path}")
        path.touch()

    @classmethod
    def use(cls, name: str) -> None:
        cls._ensure_dirs()
        path = cls._CONFIGS_DIR / f"{name}.env"
        if not path.exists():
            available = cls.list_configs()
            msg = f"Config '{name}' does not exist."
            if available:
                msg += f" Available: {', '.join(available)}"
            raise FileNotFoundError(msg)
        cls._ACTIVE_FILE.write_text(name)

    @classmethod
    def set_value(cls, key: str, value: str) -> None:
        if not _VALID_KEY.match(key):
            raise ValueError(
                f"Invalid key '{key}'. Keys must be UPPER_SNAKE_CASE (e.g. GITHUB_TOKEN)."
            )
        if "\n" in value or "\r" in value:
            raise ValueError(f"Value for '{key}' must not contain newlines.")
        config_path = Path(cls.active_config_path())
        content = config_path.read_text()
        lines = content.splitlines() if content.strip() else []
        new_lines: list[str] = []
        found = False
        for line in lines:
            if "=" in line and line.split("=", 1)[0].strip() == key:
                new_lines.append(f"{key}={value}")
                found = True
            else:
                new_lines.append(line)
        if not found:
            new_lines.append(f"{key}={value}")
        config_path.write_text("\n".join(new_lines) + "\n")

    @classmethod
    def get_value(cls, key: str) -> str | None:
        config_path = Path(cls.active_config_path())
        for line in config_path.read_text().splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, _, v = line.partition("=")
            if k.strip() == key:
                return v.strip()
        return None

    @classmethod
    def edit(cls) -> None:
        editor = os.environ.get("EDITOR", "nano")
        try:
            subprocess.run([*shlex.split(editor), cls.active_config_path()], check=True)
        except subprocess.CalledProcessError as e:
            raise RuntimeError(f"Editor exited with error (code {e.returncode}).") from e

    @classmethod
    def show(cls) -> dict[str, str]:
        config_path = Path(cls.active_config_path())
        result: dict[str, str] = {}
        for line in config_path.read_text().splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, _, v = line.partition("=")
            k = k.strip()
            v = v.strip()
            result[k] = "***" if cls._SENSITIVE.search(k) else v
        return result

    @classmethod
    def list_configs(cls) -> list[str]:
        cls._ensure_dirs()
        return sorted(p.stem for p in cls._CONFIGS_DIR.glob("*.env"))
