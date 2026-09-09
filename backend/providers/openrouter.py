"""OpenRouter provider — primary `OPENROUTER_API_1`, fallback `OPENROUTER_API_2`.

Failover activates on rate limits, quota exhaustion, auth failures and transient
server errors. Retries are bounded with exponential backoff; secrets are never
logged (keys are passed in headers only).
"""
from __future__ import annotations

import asyncio
import time
from typing import Any, Optional

import httpx

from backend.events import event_bus
from backend.logging_utils import get_logger, log_json
from backend.models.schemas import AgentEvent
from backend.providers.base import (
    RETRYABLE_STATUS,
    BaseProvider,
    ProviderError,
    ProviderResult,
)

log = get_logger("providers.openrouter")

OPENROUTER_BASE = "https://openrouter.ai/api/v1"
MAX_ATTEMPTS_PER_KEY = 2
BACKOFF_BASE = 1.5
BACKOFF_INITIAL = 1.0
BACKOFF_MAX = 12.0


def _classify(status: int) -> tuple[bool, bool]:
    """Return (retry_same_key, failover_to_next)."""
    if status in (401, 402, 403):          # auth / quota exhausted / forbidden
        return False, True
    if status == 429:                       # rate limited
        return False, True
    if status in RETRYABLE_STATUS - {429}:
        return True, False
    return False, False                     # 4xx client error: do not retry


class OpenRouterProvider(BaseProvider):
    name = "openrouter"

    def __init__(self, key_1: str, key_2: str) -> None:
        self.key_1 = (key_1 or "").strip()
        self.key_2 = (key_2 or "").strip()

    def keys(self) -> list[str]:
        return [k for k in (self.key_1, self.key_2) if k]

    def available(self) -> bool:
        return bool(self.keys())

    @property
    def safe_status(self) -> dict[str, Any]:
        return {
            "provider": self.name,
            "available": self.available(),
            "keys_configured": len(self.keys()),
        }

    def set_keys(self, key_1: str, key_2: str) -> None:
        self.key_1 = (key_1 or "").strip()
        self.key_2 = (key_2 or "").strip()

    async def generate(
        self,
        messages: list[dict[str, str]],
        model: str,
        *,
        temperature: float = 0.2,
        max_tokens: int = 2048,
        timeout: float = 60.0,
    ) -> ProviderResult:
        keys = self.keys()
        if not keys:
            raise ProviderError(self.name, "no OpenRouter keys configured", failover=True)
        if not model:
            raise ProviderError(self.name, "no model selected", failover=True)

        last_error: Optional[ProviderError] = None
        for key_index, key in enumerate(keys):
            try:
                return await self._generate_with_key(
                    messages, model, key, key_index,
                    temperature=temperature, max_tokens=max_tokens, timeout=timeout,
                )
            except ProviderError as exc:
                last_error = exc
                if not exc.failover:
                    raise
                log_json(log, 30, "openrouter_key_failover",
                         key_index=key_index, status=exc.status, reason=str(exc))
                continue
        assert last_error is not None
        raise last_error

    async def _generate_with_key(
        self,
        messages: list[dict[str, str]],
        model: str,
        key: str,
        key_index: int,
        *,
        temperature: float,
        max_tokens: int,
        timeout: float,
    ) -> ProviderResult:
        headers = {
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://colum.local",
            "X-Title": "COLUM",
        }
        payload = {
            "model": model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }

        backoff = BACKOFF_INITIAL
        for attempt in range(1, MAX_ATTEMPTS_PER_KEY + 1):
            await event_bus.publish(AgentEvent(event="provider_request", data={
                "provider": self.name, "model": model, "key_index": key_index, "attempt": attempt,
            }))
            started = time.monotonic()
            try:
                async with httpx.AsyncClient(timeout=timeout, follow_redirects=False) as client:
                    resp = await client.post(
                        f"{OPENROUTER_BASE}/chat/completions",
                        headers=headers, json=payload,
                    )
            except httpx.TimeoutException as exc:
                if attempt < MAX_ATTEMPTS_PER_KEY:
                    await asyncio.sleep(backoff)
                    backoff = min(backoff * BACKOFF_BASE, BACKOFF_MAX)
                    continue
                raise ProviderError(self.name, f"request timeout after {timeout}s: {exc}",
                                    status=408, retryable=True, failover=False)
            except httpx.HTTPError as exc:
                if attempt < MAX_ATTEMPTS_PER_KEY:
                    await asyncio.sleep(backoff)
                    backoff = min(backoff * BACKOFF_BASE, BACKOFF_MAX)
                    continue
                raise ProviderError(self.name, f"network error: {type(exc).__name__}",
                                    retryable=True, failover=False)

            duration_ms = int((time.monotonic() - started) * 1000)
            if resp.status_code == 200:
                try:
                    body = resp.json()
                except ValueError as exc:
                    raise ProviderError(self.name, "malformed JSON in provider response",
                                        failover=False)
                usage = body.get("usage") or {}
                choice = (body.get("choices") or [{}])[0]
                text = (choice.get("message") or {}).get("content") or ""
                log_json(log, 20, "openrouter_ok", model=model, key_index=key_index,
                         duration_ms=duration_ms, prompt_tokens=usage.get("prompt_tokens", 0))
                return ProviderResult(
                    text=text, provider=self.name, model=model,
                    prompt_tokens=int(usage.get("prompt_tokens") or 0),
                    completion_tokens=int(usage.get("completion_tokens") or 0),
                    total_tokens=int(usage.get("total_tokens")
                                     or (usage.get("prompt_tokens") or 0)
                                     + (usage.get("completion_tokens") or 0)),
                    key_index=key_index, raw={"id": body.get("id", "")},
                )

            retry_same, failover_next = _classify(resp.status_code)
            detail = _error_detail(resp)
            log_json(log, 30, "openrouter_error", model=model, key_index=key_index,
                     status=resp.status_code, duration_ms=duration_ms, detail=detail)
            if failover_next:
                raise ProviderError(self.name, f"HTTP {resp.status_code}: {detail}",
                                    status=resp.status_code, failover=True)
            if retry_same and attempt < MAX_ATTEMPTS_PER_KEY:
                await asyncio.sleep(backoff)
                backoff = min(backoff * BACKOFF_BASE, BACKOFF_MAX)
                continue
            raise ProviderError(self.name, f"HTTP {resp.status_code}: {detail}",
                                status=resp.status_code, retryable=retry_same, failover=False)

        raise ProviderError(self.name, "exhausted attempts", failover=False)


def _error_detail(resp: httpx.Response) -> str:
    """Human-safe error detail (provider messages, no echo of auth headers)."""
    try:
        body = resp.json()
        msg = (body.get("error") or {}).get("message") or str(body)[:200]
    except ValueError:
        msg = resp.text[:200]
    return msg.replace("\n", " ")[:300]
