"""Per-user access keys + daily run cap — the app's access gate and cost guard.

The frontend collects a user's access key once and gates the chat on it. Only SHA-256 hashes are
stored, so a config/store leak exposes no usable key. Two backends via ``API_KEY_STORE``:

- ``env``   — keys from the ``API_KEYS`` list (``name:hash``); in-process counts. (demo default)
- ``table`` — keys looked up per request in Azure Table Storage (keyless via Entra ID), with
  durable, etag-guarded daily counts. Add/revoke users with ``utils/add_user.py`` (no redeploy).

Public surface (used by the frontend, no FastAPI):

    auth_enabled() -> bool
    validate_key(key) -> name | None              # is this key allowed?
    consume_run(key) -> (ok, name|None, message)  # validate + count one run against the daily cap
"""

from __future__ import annotations

import hashlib
import logging
from abc import ABC, abstractmethod
from datetime import UTC, datetime
from functools import lru_cache

from deep_research.config import get_settings

logger = logging.getLogger(__name__)

_KEY_PARTITION = "key"
_MAX_CONSUME_RETRIES = 3


def hash_key(key: str) -> str:
    """Return the SHA-256 hex digest of a key."""
    return hashlib.sha256(key.encode()).hexdigest()


def _today() -> str:
    return datetime.now(UTC).date().isoformat()


# --- store interface ---------------------------------------------------------


class KeyStore(ABC):
    """A source of allowed API keys + per-key daily run accounting."""

    @property
    @abstractmethod
    def enabled(self) -> bool:
        """True when auth is active (False => the gate is open, local dev)."""

    @abstractmethod
    async def name_for(self, key_hash: str) -> str | None:
        """Return the user name for an allowed key hash, or None if not allowed."""

    @abstractmethod
    async def try_consume(self, key_hash: str, limit: int) -> bool:
        """Count one accepted run; return False if the daily ``limit`` is exceeded."""

    async def aclose(self) -> None:  # noqa: B027 - optional hook; default no-op
        """Release any underlying clients (overridden where needed)."""


# --- env-backed store (demo default) ----------------------------------------
_env_runs: dict[tuple[str, str], int] = {}


def reset_counts() -> None:
    """Clear the in-process daily run counters (env store; used by tests)."""
    _env_runs.clear()


class EnvKeyStore(KeyStore):
    """Keys from the ``API_KEYS`` env list; in-process daily counts."""

    @property
    def enabled(self) -> bool:
        return bool(self._allowed())

    def _allowed(self) -> dict[str, str]:
        allowed: dict[str, str] = {}
        for entry in get_settings().api_keys.split(","):
            entry = entry.strip()
            if not entry:
                continue
            name, _, digest = entry.rpartition(":")
            allowed[digest.strip().lower()] = name.strip() or "user"
        return allowed

    async def name_for(self, key_hash: str) -> str | None:
        return self._allowed().get(key_hash)

    async def try_consume(self, key_hash: str, limit: int) -> bool:
        if not limit:
            return True
        today = _today()
        used = _env_runs.get((key_hash, today), 0)
        if used >= limit:
            return False
        _env_runs[(key_hash, today)] = used + 1
        return True


# --- Azure Table Storage store ----------------------------------------------


class TableKeyStore(KeyStore):
    """Keys + durable daily counts in Azure Table Storage (keyless via Entra ID)."""

    def __init__(self, table_client) -> None:
        self._client = table_client

    @property
    def enabled(self) -> bool:
        return True

    async def name_for(self, key_hash: str) -> str | None:
        from azure.core.exceptions import ResourceNotFoundError

        try:
            entity = await self._client.get_entity(_KEY_PARTITION, key_hash)
        except ResourceNotFoundError:
            return None
        except Exception as exc:  # noqa: BLE001 - treat lookup errors as "not allowed"
            logger.warning("Key lookup failed: %s", exc)
            return None
        if not entity.get("Active", True):
            return None
        return entity.get("Name") or "user"

    async def try_consume(self, key_hash: str, limit: int) -> bool:
        if not limit:
            return True
        try:
            return await self._consume(key_hash, limit)
        except Exception as exc:  # noqa: BLE001 - availability over strict enforcement
            logger.warning("Rate-limit accounting failed (allowing run): %s", exc)
            return True  # fail open

    async def _consume(self, key_hash: str, limit: int) -> bool:
        from azure.core import MatchConditions
        from azure.core.exceptions import (
            ResourceExistsError,
            ResourceModifiedError,
            ResourceNotFoundError,
        )
        from azure.data.tables import UpdateMode

        partition = f"usage:{key_hash}"
        today = _today()
        for _ in range(_MAX_CONSUME_RETRIES):
            etag = None
            count = 0
            try:
                current = await self._client.get_entity(partition, today)
                count = int(current.get("Count", 0))
                etag = current.metadata.get("etag")
            except ResourceNotFoundError:
                pass
            if count >= limit:
                return False
            entity = {"PartitionKey": partition, "RowKey": today, "Count": count + 1}
            try:
                if etag:
                    await self._client.update_entity(
                        entity,
                        mode=UpdateMode.REPLACE,
                        etag=etag,
                        match_condition=MatchConditions.IfNotModified,
                    )
                else:
                    await self._client.create_entity(entity)
                return True
            except (ResourceModifiedError, ResourceExistsError):
                continue  # lost the race; re-read and retry
        return True  # could not settle under contention; allow rather than block

    async def aclose(self) -> None:
        await self._client.close()


# --- factory + public helpers -----------------------------------------------


@lru_cache(maxsize=1)
def get_key_store() -> KeyStore:
    """Return the configured key store (cached). Env unless API_KEY_STORE=table."""
    cfg = get_settings()
    if cfg.api_key_store == "table" and cfg.azure_table_endpoint:
        from azure.data.tables.aio import TableClient
        from azure.identity.aio import DefaultAzureCredential

        client = TableClient(
            endpoint=cfg.azure_table_endpoint,
            table_name=cfg.api_keys_table,
            credential=DefaultAzureCredential(),
        )
        return TableKeyStore(client)
    return EnvKeyStore()


def reset_store() -> None:
    """Clear in-process counters + the cached store (used by tests)."""
    reset_counts()
    get_key_store.cache_clear()


def auth_enabled() -> bool:
    """True when an access key is required (an env key list is set, or the table store is on)."""
    return get_key_store().enabled


async def validate_key(key: str | None) -> str | None:
    """Return the caller's name for a valid key, else None. (No rate-limit increment.)"""
    store = get_key_store()
    if not store.enabled:
        return "anonymous"
    if not key:
        return None
    return await store.name_for(hash_key(key))


async def consume_run(key: str | None) -> tuple[bool, str | None, str]:
    """Validate ``key`` and count one research run against the daily cap.

    Returns ``(ok, name, message)``: ``ok=False`` with a message on an invalid key or when the
    daily limit is reached. Call this once when a user starts a research run.
    """
    name = await validate_key(key)
    if name is None:
        return False, None, "Invalid or missing access key."
    if name == "anonymous":
        return True, name, ""
    limit = get_settings().max_runs_per_key_per_day
    if not await get_key_store().try_consume(hash_key(key or ""), limit):
        return False, name, f"Daily run limit ({limit}) reached. Try again tomorrow."
    return True, name, ""
