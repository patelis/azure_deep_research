"""Azure Monitor + OpenTelemetry tracing — observability as a first-class citizen.

Resolves the Application Insights connection string (env or Foundry project), configures Azure
Monitor, and instruments OpenAI model calls plus the Azure AI Agents SDK. Business-logic phases
are also wrapped in manual spans:

    clarify -> plan -> lead:round{n} -> researcher:<topic> -> report -> email

Prompt/completion *content* capture is gated behind ``TRACE_CONTENT`` (privacy: off by default).
"""

from __future__ import annotations

import contextlib
import logging
import os
from typing import Any

from opentelemetry import trace

from deep_research.config import get_settings

logger = logging.getLogger(__name__)

_TRACER_NAME = "deep_research"
_initialized = False
_tracer: trace.Tracer | None = None


def _resolve_connection_string() -> str | None:
    """Resolve the App Insights connection string from env, else the Foundry project."""
    cfg = get_settings()
    if cfg.applicationinsights_connection_string:
        return cfg.applicationinsights_connection_string
    if cfg.azure_ai_project_endpoint:
        try:
            from azure.ai.projects import AIProjectClient

            from deep_research.azure_client import get_credential

            project = AIProjectClient(
                endpoint=cfg.azure_ai_project_endpoint, credential=get_credential()
            )
            return project.telemetry.get_application_insights_connection_string()
        except Exception as exc:  # noqa: BLE001
            logger.warning("Could not fetch App Insights connection string: %s", exc)
    return None


def _instrument_foundry_agents() -> None:
    """Emit OpenTelemetry spans for Foundry agent runs (threads/runs/tool calls)."""
    try:
        from azure.ai.agents.telemetry import AIAgentsInstrumentor

        AIAgentsInstrumentor().instrument()
        logger.info("Azure AI Agents instrumented for OpenTelemetry.")
    except Exception:  # noqa: BLE001 - optional; manual phase spans still apply
        logger.info("AIAgentsInstrumentor unavailable; relying on manual spans + OpenAI traces.")


def setup_observability() -> trace.Tracer | None:
    """Configure Azure Monitor + OpenTelemetry once; return the pipeline tracer."""
    global _initialized, _tracer
    if _initialized:
        return _tracer

    cfg = get_settings()
    if not cfg.enable_tracing:
        _initialized = True
        return None

    # Capture gen-ai message content in spans only when explicitly enabled (privacy).
    if cfg.trace_content:
        os.environ.setdefault("OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT", "true")
        os.environ.setdefault("AZURE_TRACING_GEN_AI_CONTENT_RECORDING_ENABLED", "true")

    conn = _resolve_connection_string()
    if not conn:
        logger.warning(
            "No Application Insights connection string; traces will not be exported. "
            "Set APPLICATIONINSIGHTS_CONNECTION_STRING or AZURE_AI_PROJECT_ENDPOINT."
        )
        _instrument_foundry_agents()
        _initialized = True
        _tracer = trace.get_tracer(_TRACER_NAME)
        return _tracer

    from azure.monitor.opentelemetry import configure_azure_monitor

    configure_azure_monitor(connection_string=conn)
    try:
        from opentelemetry.instrumentation.openai_v2 import OpenAIInstrumentor

        OpenAIInstrumentor().instrument()
    except Exception as exc:  # noqa: BLE001
        logger.warning("OpenAI instrumentation unavailable: %s", exc)

    _instrument_foundry_agents()
    _initialized = True
    _tracer = trace.get_tracer(_TRACER_NAME)
    logger.info("Azure Monitor tracing configured.")
    return _tracer


def get_tracer() -> trace.Tracer | None:
    """Return the configured tracer (or None if tracing is off/not yet set up)."""
    return _tracer


@contextlib.contextmanager
def span(name: str, **attributes: Any):
    """Start a named span with attributes; a no-op when tracing is disabled."""
    if _tracer is None:
        yield None
        return
    with _tracer.start_as_current_span(name) as current:
        for key, value in attributes.items():
            if value is not None:
                current.set_attribute(key, value)
        yield current


def shutdown_observability() -> None:
    """Flush pending telemetry before the process exits."""
    provider = trace.get_tracer_provider()
    flush = getattr(provider, "force_flush", None)
    if callable(flush):
        with contextlib.suppress(Exception):
            flush()
