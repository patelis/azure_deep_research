"""Input guardrail: Azure AI Content Safety Prompt Shields.

Screens each incoming query for prompt injection / jailbreak before any model call, complementing
the model-level RAI content filter on the deployments (defense in depth). Config-gated
(``ENABLE_CONTENT_SAFETY``) and fail-open by default (``CONTENT_SAFETY_FAIL_OPEN``) so a safety
hiccup degrades to "allowed" rather than breaking a demo. Keyless via Entra ID.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from deep_research.config import get_settings

logger = logging.getLogger(__name__)

_SHIELD_SCOPE = "https://cognitiveservices.azure.com/.default"
_SHIELD_API_VERSION = "2024-09-01"


@dataclass
class GuardrailResult:
    """Outcome of an input guardrail check."""

    allowed: bool
    reason: str = ""


async def check_prompt(text: str) -> GuardrailResult:
    """Screen a user query with Prompt Shields; allow unless an attack is detected."""
    cfg = get_settings()
    if not cfg.enable_content_safety or not cfg.content_safety_endpoint:
        return GuardrailResult(True)

    try:
        import httpx

        from deep_research.azure_client import get_credential

        token = get_credential().get_token(_SHIELD_SCOPE).token
        endpoint = cfg.content_safety_endpoint.rstrip("/")
        url = f"{endpoint}/contentsafety/text:shieldPrompt?api-version={_SHIELD_API_VERSION}"
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(
                url,
                headers={"Authorization": f"Bearer {token}"},
                json={"userPrompt": text, "documents": []},
            )
            resp.raise_for_status()
            data = resp.json()

        attack = data.get("userPromptAnalysis", {}).get("attackDetected", False)
        if attack:
            return GuardrailResult(
                False, "The request was flagged as a prompt-injection / jailbreak attempt."
            )
        return GuardrailResult(True)
    except Exception as exc:  # noqa: BLE001 - guardrail availability must not break the run
        if cfg.content_safety_fail_open:
            logger.warning("Content Safety check failed open: %s", exc)
            return GuardrailResult(True)
        return GuardrailResult(False, "Safety screening is unavailable; request rejected.")
