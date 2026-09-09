"""Custom OpenAI-compatible provider (user-configured endpoint/key/model)."""
from __future__ import annotations

import time
from typing import Any

import httpx

from backend.events import event_bus
from backend.logging_utils import get_logger, log_json
from backend.models.schemas import AgentEvent
from backend.providers.base import BaseProvider, ProviderError, ProviderResult

log = get_logger("providers.custom")


class CustomProvider(BaseProvider):
    name = "custom"

    def __init__(self, name: str, endpoint: str, api_key: str, model: str,
                 headers: dict[str, str] | None = None) -> None:
        self.display_name = name or "custom"
        self.endpoint = (endpoint or "").rstrip("/")
        self.api_key = api_key or ""
        self.model_default = model or ""
        self.extra_headers = headers or {}

    def available(self) -> bool:
        return bool(self.endpoint and self.model_default)

    @property
    def safe_status(self) -> dict[str, Any]:
        return {
            "provider": self.name,
            "display_name": self.display_name,
            "available": self.available(),
            "endpoint": self.endpoint,
            "model": self.model_default,
            "has_key": bool(self.api_key),
        }

    async def generate(
        self,
        messages: list[dict[str, str]],
        model: str,
        *,
        temperature: float = 0.2,
        max_tokens: int = 2048,
        timeout: float = 60.0,
    ) -> ProviderResult:
        if not self.available():
            raise ProviderError(self.name, "custom provider not fully configured", failover=True)
        target_model = model or self.model_default
        headers = {"Content-Type": "application/json", **self.extra_headers}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"

        payload = {
            "model": target_model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        await event_bus.publish(AgentEvent(event="provider_request", data={
            "provider": self.display_name, "model": target_model,
        }))
        started = time.monotonic()
        try:
            async with httpx.AsyncClient(timeout=timeout, follow_redirects=False) as client:
                resp = await client.post(f"{self.endpoint}/chat/completions",
                                         headers=headers, json=payload)
        except httpx.TimeoutException as exc:
            raise ProviderError(self.name, f"request timeout after {timeout}s: {exc}",
                                status=408, retryable=False)
        except httpx.HTTPError as exc:
            raise ProviderError(self.name, f"network error: {type(exc).__name__}")

        duration_ms = int((time.monotonic() - started) * 1000)
        if resp.status_code != 200:
            detail = _safe_detail(resp)
            log_json(log, 30, "custom_error", status=resp.status_code, duration_ms=duration_ms)
            raise ProviderError(self.name, f"HTTP {resp.status_code}: {detail}",
                                status=resp.status_code,
                                retryable=resp.status_code in (429, 500, 502, 503, 504))
        try:
            body = resp.json()
        except ValueError as exc:
            raise ProviderError(self.name, "malformed JSON in provider response")
        choice = (body.get("choices") or [{}])[0]
        usage = body.get("usage") or {}
        log_json(log, 20, "custom_ok", model=target_model, duration_ms=duration_ms)
        return ProviderResult(
            text=(choice.get("message") or {}).get("content") or "",
            provider=self.display_name, model=target_model,
            prompt_tokens=int(usage.get("prompt_tokens") or 0),
            completion_tokens=int(usage.get("completion_tokens") or 0),
            total_tokens=int(usage.get("total_tokens") or 0),
            raw={"id": body.get("id", "")},
        )


def _safe_detail(resp: httpx.Response) -> str:
    try:
        body = resp.json()
        msg = (body.get("error") or {}).get("message") or str(body)[:200]
    except ValueError:
        msg = resp.text[:200]
    return msg.replace("\n", " ")[:300]
