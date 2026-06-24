"""Configuration for the deep research backend.

All values come from the environment (or a local ``.env``); populate from the Bicep/azd outputs.
Nothing about models, the Foundry project, or supporting resources is hard-coded.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime settings, read from the environment / ``.env``."""

    model_config = SettingsConfigDict(
        # Find settings whether launched from the repo root or from backend/.
        env_file=(".env", "../.env", "../../.env"),
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # --- Azure OpenAI (Responses API: clarifier, lead orchestrator, report) ---
    azure_openai_endpoint: str = Field(default="", alias="AZURE_OPENAI_ENDPOINT")
    azure_openai_api_version: str = Field(
        default="2025-03-01-preview", alias="AZURE_OPENAI_API_VERSION"
    )
    main_model: str = Field(default="gpt-4.1", alias="MAIN_MODEL")
    mini_model: str = Field(default="gpt-4.1-mini", alias="MINI_MODEL")
    openai_max_retries: int = Field(default=5, alias="OPENAI_MAX_RETRIES")

    # --- Azure AI Foundry project + Grounding with Bing ---
    azure_ai_project_endpoint: str = Field(default="", alias="AZURE_AI_PROJECT_ENDPOINT")
    bing_connection_id: str = Field(default="", alias="BING_CONNECTION_ID")
    # The app resolves agent ids at runtime by these stable names (see utils/sync_agents.py).
    lead_agent_name: str = Field(default="deep-research-lead", alias="LEAD_AGENT_NAME")
    researcher_agent_name: str = Field(
        default="deep-research-researcher", alias="RESEARCHER_AGENT_NAME"
    )
    report_agent_name: str = Field(default="deep-research-report", alias="REPORT_AGENT_NAME")

    # --- Orchestration caps (cost guards) ---
    # Hard ceiling on researcher sub-agents per run (code-enforced).
    max_subagents_per_run: int = Field(default=5, alias="MAX_SUBAGENTS_PER_RUN")
    # Concurrency cap on researchers (semaphore).
    max_parallel_researchers: int = Field(default=3, alias="MAX_PARALLEL_RESEARCHERS")
    # How many times the lead may re-plan/delegate.
    max_delegation_rounds: int = Field(default=3, alias="MAX_DELEGATION_ROUNDS")
    # Max subtasks the lead may request in a single delegation round.
    subagents_per_round: int = Field(default=3, alias="SUBAGENTS_PER_ROUND")
    # SOFT cap on researcher web searches: injected into the researcher prompt (managed Bing
    # grounding is server-side, so this cannot be code-enforced — see the hard guards above).
    max_searches_per_researcher: int = Field(default=5, alias="MAX_SEARCHES_PER_RESEARCHER")
    # Per-researcher completion-token cap (0 = unset) — bounds spend per sub-agent.
    researcher_max_completion_tokens: int = Field(
        default=0, alias="RESEARCHER_MAX_COMPLETION_TOKENS"
    )
    # Interactive clarification turns before a plan is produced regardless.
    max_clarify_rounds: int = Field(default=3, alias="MAX_CLARIFY_ROUNDS")

    # --- Observability ---
    applicationinsights_connection_string: str = Field(
        default="", alias="APPLICATIONINSIGHTS_CONNECTION_STRING"
    )
    enable_tracing: bool = Field(default=True, alias="ENABLE_TRACING")
    # Capture prompt/completion content in spans (privacy-sensitive; off by default).
    trace_content: bool = Field(default=False, alias="TRACE_CONTENT")

    # --- Content safety (input guardrail / Prompt Shields) ---
    content_safety_endpoint: str = Field(default="", alias="AZURE_CONTENT_SAFETY_ENDPOINT")
    enable_content_safety: bool = Field(default=True, alias="ENABLE_CONTENT_SAFETY")
    content_safety_fail_open: bool = Field(default=True, alias="CONTENT_SAFETY_FAIL_OPEN")

    # --- Access control (per-user keys) ---
    api_key_store: Literal["env", "table"] = Field(default="env", alias="API_KEY_STORE")
    # Comma-separated allowed keys as ``name:sha256hex``. Empty disables the gate (local dev).
    api_keys: str = Field(default="", alias="API_KEYS")
    azure_table_endpoint: str = Field(default="", alias="AZURE_TABLE_ENDPOINT")
    api_keys_table: str = Field(default="apikeys", alias="API_KEYS_TABLE")
    max_runs_per_key_per_day: int = Field(default=3, alias="MAX_RUNS_PER_KEY_PER_DAY")

    # --- Email (Azure Communication Services) ---
    acs_connection_string: str = Field(default="", alias="ACS_CONNECTION_STRING")
    acs_sender_address: str = Field(default="", alias="ACS_SENDER_ADDRESS")


@lru_cache
def get_settings() -> Settings:
    """Return the cached, process-wide settings instance."""
    return Settings()
