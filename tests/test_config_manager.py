"""Tests for ConfigManager's config-file template generation."""
from __future__ import annotations

from pathlib import Path

import pytest

from haive.config.manager import ConfigManager


@pytest.fixture(autouse=True)
def _isolate_haive_dir(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(ConfigManager, "_HAIVE_DIR", tmp_path)
    monkeypatch.setattr(ConfigManager, "_CONFIGS_DIR", tmp_path / "configs")
    monkeypatch.setattr(ConfigManager, "_ACTIVE_FILE", tmp_path / "active")
    monkeypatch.setattr(ConfigManager, "_STATE_DIR", tmp_path / "state")


class TestCreate:
    def test_writes_required_keys_uncommented(self):
        ConfigManager.create("myconfig")
        content = (ConfigManager._CONFIGS_DIR / "myconfig.env").read_text()
        for key in ("GITHUB_TOKEN=", "GITHUB_REPO=", "GITHUB_PROJECT_ID="):
            assert key in content.splitlines()

    def test_writes_optional_keys_commented_with_defaults(self):
        ConfigManager.create("myconfig")
        content = (ConfigManager._CONFIGS_DIR / "myconfig.env").read_text()
        assert "# MAX_WAVES_PER_RUN=2" in content
        assert "# OLLAMA_API_BASE=http://localhost:11434" in content

    def test_set_value_fills_in_a_required_placeholder_in_place(self):
        ConfigManager.create("myconfig")
        ConfigManager.use("myconfig")
        ConfigManager.set_value("GITHUB_TOKEN", "ghp_xxx")
        content = (ConfigManager._CONFIGS_DIR / "myconfig.env").read_text()
        assert "GITHUB_TOKEN=ghp_xxx" in content.splitlines()
        assert content.count("GITHUB_TOKEN") == 1


class TestBootstrapDefault:
    def test_active_config_path_bootstraps_default_with_template(self):
        path = Path(ConfigManager.active_config_path())
        content = path.read_text()
        assert "GITHUB_TOKEN=" in content.splitlines()
        assert "# MAX_EXECUTORS=4" in content
