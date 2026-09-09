"""Ollama local provider — probes availability honestly; never pretends to run."""
from __future__ import annotations

import time
from typing import Any

import httpx

from backend.events import event_bus
from backend.logging_utils import get_logger, log_json
from backend.models.schemas import AgentEvent
from backend.providers.base import BaseProvider, ProviderError, ProviderResult

log = get_logger("providers.ollama")


class OllamaProvider(BaseProvider):
    name = "ollama"

    def __init__(self, base_url: str, model: str, enabled: bool = False) -> None:
        self.base_url = (base_url or "http://localhost:11434").rstrip("/")
        self.model_default = model or ""
        self.enabled = enabled

    def available(self) -> bool:
        return bool(self.enabled and self.model_default)

    @property
    def safe_status(self) -> dict[str, Any]:
        return {
            "provider": self.name,
            "available": self.available(),
            "base_url": self.base_url,
            "model": self.model_default,
            "enabled": self.enabled,
        }

    async def generate(
        self,
        messages: list[dict[str, str]],
        model: str,
        *,
        temperature: float = 0.2,
        max_tokens: int = 2048,
        timeout: float = 120.0,
    ) -> ProviderResult:
        if not self.available():
            raise ProviderError(self.name, "Ollama is not enabled or has no model", failover=True)
        target_model = model or self.model_default
        payload = {
            "model": target_model,
            "messages": messages,
            "stream": False,
            "options": {"temperature": temperature, "num_predict": max_tokens},
        }
        await event_bus.publish(AgentEvent(event="provider_request", data={
            "provider": self.name, "model": target_model,
        }))
        started = time.monotonic()
        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                resp = await client.post(f"{self.base_url}/api/chat", json=payload)
        except httpx.TimeoutException as exc:
            raise ProviderError(self.name, f"Ollama timeout after {timeout}s: {exc}", status=408)
        except httpx.HTTPError as exc:
            raise ProviderError(
                self.name,
                f"Ollama unreachable at {self.base_url} ({type(exc).__name__}). "
                "Ensure Ollama is installed and running (`ollama serve`).",
            )
        duration_ms = int((time.monotonic() - started) * 1000)
        if resp.status_code != 200:
            raise ProviderError(self.name, f"Ollama HTTP {resp.status_code}: {resp.text[:200]}",
                                status=resp.status_code)
        try:
            body = resp.json()
        except ValueError as exc:
            raise ProviderError(self.name, "malformed JSON from Ollama")
        text = body.get("message", {}).get("content", "")
        if not text:
            raise ProviderError(self.name, "Ollama returned an empty completion")
        eval_counts = body.get("prompt_eval_count"), body.get("eval_count")
        log_json(log, 20, "ollama_ok", model=target_model, duration_ms=duration_ms)
        return ProviderResult(
            text=text, provider=self.name, model=target_model,
            prompt_tokens=int(eval_counts[0] or 0),
            completion_tokens=int(eval_counts[1] or 0),
            total_tokens=int((eval_counts[0] or 0) + (eval_counts[1] or 0)),
        )

    async def list_models(self) -> list[str]:
        """List locally installed Ollama models (empty when unreachable)."""
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                resp = await client.get(f"{self.base_url}/api/tags")
            if resp.status_code != 200:
                return []
            return [m.get("name", "") for m in resp.json().get("models", []) if m.get("name")]
        except httpx.HTTPError:
            return []
