"""Azure OpenAI client (keyless / Entra ID).

The shared async client for the direct Responses calls that are NOT Foundry agents (the
clarifier, and the lead orchestrator / report writer when invoked via Responses). Built lazily
so offline tests import the package without an Azure login. Foundry agents are reached via
``runtime`` instead.
"""

from __future__ import annotations

from functools import lru_cache

from azure.identity import DefaultAzureCredential, get_bearer_token_provider
from openai import AsyncAzureOpenAI

from deep_research.config import get_settings

_COGNITIVE_SCOPE = "https://cognitiveservices.azure.com/.default"


@lru_cache(maxsize=1)
def get_credential() -> DefaultAzureCredential:
    """Return a cached ``DefaultAzureCredential`` (uses ``az login`` locally, MI in the cloud)."""
    return DefaultAzureCredential()


@lru_cache(maxsize=1)
def get_async_azure_openai_client() -> AsyncAzureOpenAI:
    """Build the keyless async Azure OpenAI client used for the Responses API calls."""
    cfg = get_settings()
    token_provider = get_bearer_token_provider(get_credential(), _COGNITIVE_SCOPE)
    return AsyncAzureOpenAI(
        azure_endpoint=cfg.azure_openai_endpoint,
        azure_ad_token_provider=token_provider,
        api_version=cfg.azure_openai_api_version,
        # Exponential backoff on 429/5xx (honors Retry-After) so transient throttling under
        # parallel research doesn't fail calls.
        max_retries=cfg.openai_max_retries,
    )
