from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic_settings.sources.base import PydanticBaseSettingsSource
from pydantic_settings.sources.providers.dotenv import DotEnvSettingsSource
from pydantic.fields import FieldInfo

from haive.models.enums import AgentRole


class _CsvDotEnvSource(DotEnvSettingsSource):
    """DotEnv source that accepts comma-separated strings for list fields."""

    def prepare_field_value(
        self, field_name: str, field: FieldInfo, value: Any, value_is_complex: bool
    ) -> Any:
        if isinstance(value, str):
            stripped = value.strip()
            if stripped and not stripped.startswith(("[", "{")):
                is_complex, _ = self._field_is_complex(field)
                if is_complex or value_is_complex:
                    return [p.strip() for p in stripped.split(",") if p.strip()]
        return super().prepare_field_value(field_name, field, value, value_is_complex)


class Settings(BaseSettings):
    # TODO : revert hard coded values back to env
    model_config = SettingsConfigDict(extra="ignore")

    # Low tier
    tier_low_models: list[str]
    tier_low_max_attempts: int = 2
    tier_low_context_budget: int = 8000

    # Medium tier
    tier_medium_models: list[str]
    tier_medium_max_attempts: int = 2
    tier_medium_context_budget: int = 16000

    # High tier
    tier_high_models: list[str]
    tier_high_max_attempts: int = 2
    tier_high_context_budget: int = 32000

    # Review agent
    reviewer_models: list[str]

    # Recovery
    max_recovery_depth: int = 3

    # Concurrency
    max_executors: int = 4

    # Providers
    anthropic_api_key: str | None = None
    openai_api_key: str | None = None
    ollama_api_base: str = "http://localhost:11434"

    # Adapter selection
    pm_adapter: Literal["github"] = "github"
    vcs_adapter: Literal["github"] = "github"

    # GitHub (required when either adapter is "github")
    github_token: str | None = None
    github_repo: str | None = None
    github_project_id: int | None = None      # Projects v2 board number — shared, set once
    github_milestone_id: int | None = None    # default milestone for haive run (optional; --project overrides)

    @model_validator(mode="after")
    def validate_github_credentials(self) -> "Settings":
        if self.pm_adapter == "github" or self.vcs_adapter == "github":
            if not self.github_token:
                raise ValueError(
                    "GITHUB_TOKEN is required when using the GitHub adapter"
                )
            if not self.github_repo:
                raise ValueError(
                    "GITHUB_REPO is required when using the GitHub adapter"
                )
            if not self.github_project_id:
                raise ValueError(
                    "GITHUB_PROJECT_ID is required when using the GitHub adapter"
                )
        return self

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls: type[BaseSettings],
        init_settings: PydanticBaseSettingsSource,
        env_settings: PydanticBaseSettingsSource,
        dotenv_settings: PydanticBaseSettingsSource,
        file_secret_settings: PydanticBaseSettingsSource,
    ) -> tuple[PydanticBaseSettingsSource, ...]:
        assert isinstance(dotenv_settings, DotEnvSettingsSource)
        csv_dotenv = _CsvDotEnvSource(
            settings_cls,
            env_file=dotenv_settings.env_file,
            env_file_encoding=dotenv_settings.env_file_encoding,
        )
        return (init_settings, csv_dotenv, env_settings, file_secret_settings)


def load_settings() -> Settings:
    from haive.config.manager import ConfigManager

    config_path = ConfigManager.active_config_path()
    try:
        return Settings(_env_file=config_path)
    except ValidationError as e:
        e.add_note(f"Config file: {config_path}")
        raise


class AgentConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    role:                      AgentRole
    description:               str = Field(min_length=1)
    skills:                    list[str] = Field(min_length=1)
    system_prompt:             str = Field(min_length=1)
    output_schema:             str = Field(min_length=1)
    max_tokens:                int = Field(gt=0)
    retry_limit:               int = Field(ge=0)
    prompt_version:            str = Field(min_length=1)
    context_budget_multiplier: float = Field(default=1.0, gt=0)
