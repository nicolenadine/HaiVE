"""Tests for Settings' handling of blank env values for optional int fields."""
from __future__ import annotations

import pytest
from pydantic import ValidationError

from haive.models.config import Settings


def _make(**overrides) -> Settings:
    defaults = dict(github_token="tok", github_repo="owner/repo", github_project_id=42)
    return Settings(**(defaults | overrides))


class TestBlankGithubIdFields:
    def test_blank_string_milestone_id_becomes_none(self):
        settings = _make(github_milestone_id="")
        assert settings.github_milestone_id is None

    def test_real_int_values_still_work(self):
        settings = _make(github_project_id=7, github_milestone_id=3)
        assert settings.github_project_id == 7
        assert settings.github_milestone_id == 3

    def test_blank_project_id_surfaces_friendly_required_error_not_parsing_error(self):
        with pytest.raises(ValidationError, match="GITHUB_PROJECT_ID is required"):
            Settings(github_token="tok", github_repo="owner/repo", github_project_id="")
