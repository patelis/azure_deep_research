"""Runtime bridge to the Azure AI Foundry Agent Service.

The lead, researcher, and report agents are defined in Foundry (created/updated from the prompts
by ``utils/sync_agents.py``); this module runs them. ``run_agent`` creates a thread, posts the
conversation, starts a run, and returns the final assistant text plus URL-citation sources.
Function-tool calls use a poll + submit-tool-outputs loop. Agents are looked up **by name** at
runtime (``resolve_agent_id``) so a prompt update needs no id injection or app restart. Keyless
via Entra ID; the client is built lazily so the package imports offline.
"""

from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any

from azure.ai.agents.models import (
    ListSortOrder,
    MessageRole,
    ResponseFormatJsonSchema,
    ResponseFormatJsonSchemaType,
    RunStatus,
    ToolOutput,
)

from deep_research.config import get_settings

logger = logging.getLogger(__name__)

# A tool implementation: async callable invoked with the model-supplied JSON arguments.
ToolFn = Callable[..., Awaitable[str]]
Dispatch = dict[str, ToolFn]

_POLL_INTERVAL_S = 1.0
_ACTIVE = (RunStatus.QUEUED, RunStatus.IN_PROGRESS, RunStatus.REQUIRES_ACTION)


@dataclass
class AgentResult:
    """The terminal output of a Foundry agent run."""

    text: str
    sources: list[str] = field(default_factory=list)


class FoundryRunError(RuntimeError):
    """A Foundry run ended in a non-completed terminal state."""


# --- lazy keyless client -----------------------------------------------------
_client: Any = None
_credential: Any = None
_agent_ids: dict[str, str] = {}
_resolve_lock = asyncio.Lock()


def _get_client():
    """Return a cached async ``AgentsClient`` for the configured project (keyless)."""
    global _client, _credential
    if _client is None:
        from azure.ai.agents.aio import AgentsClient
        from azure.identity.aio import DefaultAzureCredential

        cfg = get_settings()
        _credential = DefaultAzureCredential()
        _client = AgentsClient(endpoint=cfg.azure_ai_project_endpoint, credential=_credential)
    return _client


async def resolve_agent_id(name: str) -> str:
    """Resolve a Foundry agent id by its stable name (cached per process).

    Agents are created/updated by ``utils/sync_agents.py`` with deterministic names; resolving
    by name decouples the app from id injection (a prompt update keeps the same id).
    """
    if name in _agent_ids:
        return _agent_ids[name]
    async with _resolve_lock:
        if name in _agent_ids:  # double-checked under the lock
            return _agent_ids[name]
        client = _get_client()
        async for agent in client.list_agents():
            if agent.name:
                _agent_ids[agent.name] = agent.id
        if name not in _agent_ids:
            raise FoundryRunError(
                f"No Foundry agent named {name!r}. Run utils/sync_agents.py to create it."
            )
        return _agent_ids[name]


async def aclose_runtime() -> None:
    """Close the cached client + credential (call on shutdown / after a CLI run)."""
    global _client, _credential
    if _client is not None:
        await _client.close()
        _client = None
    if _credential is not None:
        await _credential.close()
        _credential = None
    _agent_ids.clear()


# --- public API --------------------------------------------------------------


def pydantic_response_format(model: type) -> ResponseFormatJsonSchemaType:
    """Build a strict JSON-schema ``response_format`` for a Pydantic model."""
    schema = _strictify(model.model_json_schema())
    return ResponseFormatJsonSchemaType(
        json_schema=ResponseFormatJsonSchema(
            name=model.__name__,
            description=(model.__doc__ or model.__name__).strip()[:256],
            schema=schema,
        )
    )


async def run_agent(
    agent_id: str,
    user_input: str | list[tuple[str, str]],
    *,
    dispatch: Dispatch | None = None,
    response_format: ResponseFormatJsonSchemaType | None = None,
    max_completion_tokens: int | None = None,
) -> AgentResult:
    """Run a persistent Foundry agent over ``user_input`` and return its final output.

    ``user_input`` is either a single user string or a list of ``(role, content)`` turns.
    ``dispatch`` maps tool names to local async implementations (function-tool path).
    """
    client = _get_client()
    thread = await client.threads.create()
    for role, content in _as_turns(user_input):
        msg_role = MessageRole.AGENT if role == "assistant" else MessageRole.USER
        await client.messages.create(thread_id=thread.id, role=msg_role, content=content)
    return await _run_polled(
        client, thread.id, agent_id, dispatch or {}, response_format, max_completion_tokens
    )


# --- internals ---------------------------------------------------------------


def _as_turns(user_input: str | list[tuple[str, str]]) -> list[tuple[str, str]]:
    return [("user", user_input)] if isinstance(user_input, str) else list(user_input)


async def _run_polled(
    client,
    thread_id: str,
    agent_id: str,
    dispatch: Dispatch,
    response_format: ResponseFormatJsonSchemaType | None,
    max_completion_tokens: int | None,
) -> AgentResult:
    run = await client.runs.create(
        thread_id=thread_id,
        agent_id=agent_id,
        response_format=response_format,
        max_completion_tokens=max_completion_tokens or None,
        parallel_tool_calls=True,
    )
    while run.status in _ACTIVE:
        if run.status == RunStatus.REQUIRES_ACTION:
            tool_calls = run.required_action.submit_tool_outputs.tool_calls
            outputs = await _execute_tool_calls(tool_calls, dispatch)
            run = await client.runs.submit_tool_outputs(
                thread_id=thread_id, run_id=run.id, tool_outputs=outputs
            )
        else:
            await asyncio.sleep(_POLL_INTERVAL_S)
            run = await client.runs.get(thread_id=thread_id, run_id=run.id)

    if run.status != RunStatus.COMPLETED:
        raise FoundryRunError(
            f"run {run.id} ended {run.status}: {getattr(run, 'last_error', None)}"
        )
    return await _collect_result(client, thread_id)


async def _execute_tool_calls(tool_calls, dispatch: Dispatch) -> list[ToolOutput]:
    """Execute the model's requested function tools concurrently; return their outputs."""

    async def run_one(call) -> ToolOutput:
        name = getattr(call.function, "name", "")
        try:
            args = json.loads(getattr(call.function, "arguments", "") or "{}")
        except json.JSONDecodeError:
            args = {}
        fn = dispatch.get(name)
        if fn is None:
            output = f"Error: tool '{name}' is not available."
        else:
            try:
                output = await fn(**args)
            except Exception as exc:  # noqa: BLE001 - surface tool errors to the model
                logger.warning("Tool %s failed: %s", name, exc)
                output = f"Error running tool '{name}': {exc}"
        return ToolOutput(tool_call_id=call.id, output=str(output))

    return list(await asyncio.gather(*(run_one(c) for c in tool_calls)))


async def _collect_result(client, thread_id: str) -> AgentResult:
    """Read the most recent assistant message: concatenated text + URL-citation sources."""
    text_parts: list[str] = []
    sources: list[str] = []
    async for msg in client.messages.list(thread_id=thread_id, order=ListSortOrder.DESCENDING):
        if msg.role != MessageRole.AGENT:
            continue
        for item in msg.content or []:
            text = getattr(item, "text", None)
            if text is None:
                continue
            if getattr(text, "value", None):
                text_parts.append(text.value)
            for ann in getattr(text, "annotations", None) or []:
                citation = getattr(ann, "url_citation", None)
                url = getattr(citation, "url", None) if citation else None
                if url and url not in sources:
                    sources.append(url)
        break  # only the latest assistant message
    return AgentResult(text="\n".join(text_parts), sources=sources)


def _strictify(schema: dict) -> dict:
    """Make a Pydantic JSON schema strict (additionalProperties=false; all keys required)."""
    if not isinstance(schema, dict):
        return schema
    if schema.get("type") == "object" or "properties" in schema:
        props = schema.get("properties", {})
        schema["additionalProperties"] = False
        schema["required"] = list(props.keys())
        for sub in props.values():
            _strictify(sub)
    if isinstance(schema.get("items"), dict):  # array item schema
        _strictify(schema["items"])
    for key in ("$defs", "definitions"):  # referenced sub-schemas
        for sub in (schema.get(key) or {}).values():
            _strictify(sub)
    for combinator in ("anyOf", "allOf", "oneOf"):
        for sub in schema.get(combinator) or []:
            _strictify(sub)
    return schema
