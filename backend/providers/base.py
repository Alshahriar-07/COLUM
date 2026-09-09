"""Provider abstraction — common interface for OpenRouter, custom, and Ollama.

Rules enforced here:
- Provider failures never cause unsafe behavior (failures raise typed errors).
- Secrets are never included in error messages or logs.
"""
from __future__ import annotations

import json
import re
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Optional

from backend.logging_utils import get_logger

log = get_logger("providers")

RETRYABLE_STATUS = {408, 409, 425, 429, 500, 502, 503, 504}


class ProviderError(Exception):
    """A provider request failed. `status` is the HTTP status if applicable."""

    def __init__(self, provider: str, message: str, status: Optional[int] = None,
                 retryable: bool = False, failover: bool = False) -> None:
        super().__init__(message)
        self.provider = provider
        self.status = status
        self.retryable = retryable
        # failover=True means "try the next key/provider" (rate limit, quota, auth).
        self.failover = failover


@dataclass
class ProviderResult:
    text: str
    provider: str
    model: str
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    key_index: int = 0
    raw: dict[str, Any] = field(default_factory=dict)


def extract_json(text: str) -> Optional[Any]:
    """Best-effort extraction of a JSON object/array from LLM text.

    Handles plain JSON, ```json fences, and leading/trailing prose. Returns
    None when nothing parseable is found — callers must treat that as an
    agent failure, never as a valid plan.
    """
    if not text:
        return None

    # 1) fenced block ```json ... ``` (or plain ```)
    fence = re.search(r"```(?:json)?\s*(.*?)```", text, re.DOTALL)
    candidates: list[str] = []
    if fence:
        candidates.append(fence.group(1).strip())
    candidates.append(text.strip())

    # 2) first {...} or [...] balanced scan
    for opener, closer in (("{", "}"), ("[", "]")):
        start = text.find(opener)
        if start == -1:
            continue
        depth = 0
        in_str = False
        esc = False
        for i in range(start, len(text)):
            ch = text[i]
            if in_str:
                if esc:
                    esc = False
                elif ch == "\\":
                    esc = True
                elif ch == '"':
                    in_str = False
                continue
            if ch == '"':
                in_str = True
            elif ch == opener:
                depth += 1
            elif ch == closer:
                depth -= 1
                if depth == 0:
                    candidates.append(text[start:i + 1])
                    break

    for cand in candidates:
        try:
            return json.loads(cand)
        except (json.JSONDecodeError, ValueError):
            continue
    return None


class BaseProvider(ABC):
    """All providers implement `generate`; `available` reports capability honestly."""

    name: str = "base"

    @abstractmethod
    async def generate(
        self,
        messages: list[dict[str, str]],
        model: str,
        *,
        temperature: float = 0.2,
        max_tokens: int = 2048,
        timeout: float = 60.0,
    ) -> ProviderResult:
        """Generate a completion for `messages` using `model`."""

    @abstractmethod
    def available(self) -> bool:
        """Whether this provider can currently be used (keys configured etc.)."""

    @property
    @abstractmethod
    def safe_status(self) -> dict[str, Any]:
        """JSON-safe status with masked secrets for the UI/status endpoint."""
