"""Email the report as markdown via Azure Communication Services Email.

A single async helper the frontend calls when the user clicks "Send". The connection string comes
from config (a Key Vault reference in the cloud); the .md report is attached and also included as
the plain-text body. Wrapped in a span for observability.
"""

from __future__ import annotations

import base64
import re

from deep_research.config import get_settings
from deep_research.observability import span

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def is_valid_email(address: str) -> bool:
    """Lightweight syntactic check for an email address."""
    return bool(_EMAIL_RE.match(address.strip()))


async def send_report_email(
    to: str, markdown: str, *, subject: str = "Your deep research report"
) -> str:
    """Send ``markdown`` as a .md attachment to ``to``; return the ACS message id.

    Raises ``RuntimeError`` if email isn't configured or the address is invalid.
    """
    cfg = get_settings()
    if not cfg.acs_connection_string or not cfg.acs_sender_address:
        raise RuntimeError("Email is not configured (ACS_CONNECTION_STRING / ACS_SENDER_ADDRESS).")
    to = to.strip()
    if not is_valid_email(to):
        raise RuntimeError(f"Invalid email address: {to!r}")

    from azure.communication.email.aio import EmailClient

    message = {
        "senderAddress": cfg.acs_sender_address,
        "recipients": {"to": [{"address": to}]},
        "content": {
            "subject": subject,
            "plainText": markdown,
        },
        "attachments": [
            {
                "name": "report.md",
                "contentType": "text/markdown",
                "contentInBase64": base64.b64encode(markdown.encode("utf-8")).decode("ascii"),
            }
        ],
    }

    with span("email", **{"email.to": to}):
        client = EmailClient.from_connection_string(cfg.acs_connection_string)
        async with client:
            poller = await client.begin_send(message)
            result = await poller.result()
    return result.get("id", "") if isinstance(result, dict) else getattr(result, "id", "")
