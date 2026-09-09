"""Provider tests: dual-key failover, JSON extraction, router chain (stubbed transport)."""
from __future__ import annotations

import pytest

from backend.providers.base import extract_json
from backend.providers.openrouter import OpenRouterProvider, _classify


# ---------------------------------------------------------------------------
# extract_json — LLM output is never trusted
# ---------------------------------------------------------------------------

def test_extract_plain_object():
    assert extract_json('{"a": 1}') == {"a": 1}


def test_extract_fenced_json():
    text = "Here you go:\n```json\n{\"goal\": \"x\", \"steps\": []}\n```\nDone."
    assert extract_json(text) == {"goal": "x", "steps": []}


def test_extract_embedded_object_with_braces_in_strings():
    text = 'prefix {"a": "has } brace", "b": [1, 2]} suffix'
    assert extract_json(text) == {"a": "has } brace", "b": [1, 2]}


def test_extract_array():
    assert extract_json("[1, 2, 3]") == [1, 2, 3]


def test_extract_garbage_returns_none():
    assert extract_json("no json here at all") is None
    assert extract_json("") is None


def test_extract_unterminated_returns_none():
    assert extract_json('{"a": ') is None


# ---------------------------------------------------------------------------
# OpenRouter status classification
# ---------------------------------------------------------------------------

def test_auth_errors_failover():
    for status in (401, 402, 403, 429):
        retry_same, failover = _classify(status)
        assert failover is True
        assert retry_same is False


def test_server_errors_retry_same_key():
    for status in (500, 502, 503, 504, 408):
        retry_same, failover = _classify(status)
        assert retry_same is True
        assert failover is False


def test_client_errors_no_retry():
    retry_same, failover = _classify(400)
    assert retry_same is False and failover is False


# ---------------------------------------------------------------------------
# Dual-key availability + failover ordering (no network)
# ---------------------------------------------------------------------------

def test_dual_key_availability():
    p = OpenRouterProvider("k1", "")
    assert p.available() is True
    assert p.keys() == ["k1"]
    p2 = OpenRouterProvider("", "")
    assert p2.available() is False
    p3 = OpenRouterProvider("k1", "k2")
    assert p3.keys() == ["k1", "k2"]


def test_generate_without_keys_raises_failover():
    import asyncio
    from backend.providers.base import ProviderError

    async def scenario():
        p = OpenRouterProvider("", "")
        with pytest.raises(ProviderError) as ei:
            await p.generate([{"role": "user", "content": "hi"}], "m")
        assert ei.value.failover is True

    asyncio.new_event_loop().run_until_complete(scenario())


def test_no_model_raises_failover():
    import asyncio
    from backend.providers.base import ProviderError

    async def scenario():
        p = OpenRouterProvider("k", "")
        with pytest.raises(ProviderError) as ei:
            await p.generate([{"role": "user", "content": "hi"}], "")
        assert ei.value.failover is True

    asyncio.new_event_loop().run_until_complete(scenario())


# ---------------------------------------------------------------------------
# Router chain composition (settings-driven, honest availability)
# ---------------------------------------------------------------------------

def test_router_chain_empty_when_nothing_configured():
    from backend.config import settings_store
    from backend.providers.router import ProviderRouter

    router = ProviderRouter()
    s = settings_store.get()
    saved_provider = s.active_provider
    try:
        s.active_provider = "openrouter"
        # Fresh router has empty keys (provider router seeds from env; force none)
        router.openrouter.set_keys("", "")
        router.custom = router.custom  # keep as constructed from env
        if not router.custom.available():
            router.ollama.enabled = False
            chain = router.chain()
            assert chain == []
        else:
            chain = router.chain()
            assert [p.name for p in chain] == ["custom"]
    finally:
        s.active_provider = saved_provider


def test_router_chain_order_active_first():
    from backend.config import settings_store
    from backend.providers.router import ProviderRouter

    router = ProviderRouter()
    router.openrouter.set_keys("k", "")
    s = settings_store.get()
    saved = s.active_provider
    try:
        s.active_provider = "openrouter"
        chain = router.chain()
        assert chain[0].name == "openrouter"
    finally:
        s.active_provider = saved
