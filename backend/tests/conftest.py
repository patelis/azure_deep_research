"""Offline test setup: no Azure, no network. Tracing + content safety disabled by default."""

from __future__ import annotations

import os

import pytest

os.environ.setdefault("ENABLE_TRACING", "false")
os.environ.setdefault("ENABLE_CONTENT_SAFETY", "false")
os.environ.setdefault("API_KEYS", "")


@pytest.fixture(autouse=True)
def _clear_settings_cache():
    """Each test starts from a clean settings cache so env overrides take effect."""
    from deep_research.config import get_settings

    get_settings.cache_clear()
    yield
    get_settings.cache_clear()
