"""Provider router — resolves the provider+model for each agent and applies
the cross-provider fallback chain when the active provider fails.

Chain: active provider -> (custom if configured) -> (ollama if enabled).
The Master Agent's task/request-level fallback is handled here so agents stay
simple. Failures raise ProviderError after the chain is exhausted.
"""
from __future__ import annotations

import time
from typing import Any

from backend.config import config, get_settings, settings_store
from backend.logging_utils import get_logger, log_json
from backend.providers.base import BaseProvider, ProviderError, ProviderResult
from backend.providers.custom import CustomProvider
from backend.providers.ollama import OllamaProvider
from backend.providers.openrouter import OpenRouterProvider

log = get_logger("providers.router")


class ProviderRouter:
    def __init__(self) -> None:
        self.openrouter = OpenRouterProvider(
            config.openrouter_key_1, config.openrouter_key_2
        )
        self.custom = CustomProvider(
            config.custom_provider.name,
            config.custom_provider.endpoint,
            config.custom_provider.api_key,
            config.custom_provider.model,
            config.custom_provider.headers,
        )
        self.ollama = OllamaProvider(
            config.ollama.base_url, config.ollama.model, config.ollama.enabled
        )
        self._by_name: dict[str, BaseProvider] = {
            "openrouter": self.openrouter,
            "custom": self.custom,
            "ollama": self.ollama,
        }
        # Usage analytics (in-memory; left sidebar reads this)
        self.total_prompt_tokens = 0
        self.total_completion_tokens = 0
        self.total_requests = 0
        self.estimated_cost_usd = 0.0  # free models => 0; custom/ollama tracked for transparency
        self._last_failures: dict[str, str] = {}

    # ------------------------------------------------------------------
    # Settings sync
    # ------------------------------------------------------------------
    def sync_from_settings(self) -> None:
        s = settings_store.get()
        self.openrouter.set_keys(s.openrouter_key_1, s.openrouter_key_2)

    # ------------------------------------------------------------------
    # Model resolution
    # ------------------------------------------------------------------
    def model_for(self, agent: str) -> str:
        s = settings_store.get()
        return s.agent_models.get(agent) or config.default_agent_models.get(agent, "")

    def chain(self) -> list[BaseProvider]:
        """Ordered provider chain starting at the active provider."""
        s = settings_store.get()
        active = s.active_provider if s.active_provider in self._by_name else "openrouter"
        ordered: list[BaseProvider] = []
        primary = self._by_name[active]
        if primary.available():
            ordered.append(primary)
        for other_name, other in self._by_name.items():
            if other is not primary and other.available() and other_name not in (p.name for p in ordered):
                ordered.append(other)
        return ordered

    # ------------------------------------------------------------------
    # Generation with fallback
    # ------------------------------------------------------------------
    async def generate_for_agent(
        self,
        agent: str,
        system_prompt: str,
        user_prompt: str,
        *,
        temperature: float = 0.2,
        max_tokens: int = 2048,
        timeout: float = 60.0,
        require_json: bool = False,
    ) -> ProviderResult:
        """Generate using the agent's configured model; walk the chain on failure."""
        s = settings_store.get()
        requested_model = s.agent_models.get(agent) or config.default_agent_models.get(agent, "")
        chain = self.chain()
        if not chain:
            raise ProviderError(
                "router",
                "No AI provider is configured. Add an OpenRouter key in Settings, "
                "configure a custom provider, or enable Ollama.",
                failover=False,
            )

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]
        last_error: ProviderError | None = None
        for provider in chain:
            # Model selection: agents honor per-agent overrides on the active
            # provider; fallback providers use their own default model.
            model = requested_model if provider is self._by_name.get(s.active_provider) else ""
            try:
                started = time.monotonic()
                result = await provider.generate(
                    messages, model,
                    temperature=temperature, max_tokens=max_tokens, timeout=timeout,
                )
                self._record_usage(result)
                log_json(log, 20, "agent_generation", agent=agent, provider=result.provider,
                         model=result.model, duration_ms=int((time.monotonic() - started) * 1000),
                         total_tokens=result.total_tokens)
                self._last_failures.pop(agent, None)
                return result
            except ProviderError as exc:
                last_error = exc
                self._last_failures[agent] = f"{exc.provider}: {exc}"
                log_json(log, 30, "agent_generation_failed", agent=agent,
                         provider=exc.provider, status=exc.status, reason=str(exc))
                continue
        assert last_error is not None
        raise last_error

    async def simple_chat(self, text: str, *, timeout: float = 60.0) -> ProviderResult:
        """Plain chat completion via the active provider (used for summaries)."""
        s = settings_store.get()
        chain = self.chain()
        if not chain:
            raise ProviderError("router", "no provider available")
        messages = [{"role": "user", "content": text}]
        last_error: ProviderError | None = None
        for provider in chain:
            model = s.agent_models.get("master", "") if provider is self._by_name.get(s.active_provider) else ""
            try:
                result = await provider.generate(messages, model, timeout=timeout)
                self._record_usage(result)
                return result
            except ProviderError as exc:
                last_error = exc
                continue
        assert last_error is not None
        raise last_error

    # ------------------------------------------------------------------
    # Status / usage
    # ------------------------------------------------------------------
    def _record_usage(self, result: ProviderResult) -> None:
        self.total_prompt_tokens += result.prompt_tokens
        self.total_completion_tokens += result.completion_tokens
        self.total_requests += 1

    def status(self) -> dict[str, Any]:
        s = settings_store.get()
        return {
            "active_provider": s.active_provider,
            "chain": [p.safe_status for p in self.chain()],
            "openrouter": self.openrouter.safe_status,
            "custom": self.custom.safe_status,
            "ollama": self.ollama.safe_status,
            "models": {a: self.model_for(a) for a in config.default_agent_models},
            "last_failures": dict(self._last_failures),
        }

    def usage(self) -> dict[str, Any]:
        return {
            "total_prompt_tokens": self.total_prompt_tokens,
            "total_completion_tokens": self.total_completion_tokens,
            "total_tokens": self.total_prompt_tokens + self.total_completion_tokens,
            "total_requests": self.total_requests,
            "estimated_cost_usd": self.estimated_cost_usd,
        }


router = ProviderRouter()
