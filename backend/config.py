"""COLUM backend configuration.

Loads static configuration from environment/.env at import time and exposes a
thread-safe runtime settings store that the settings UI can mutate live.

Secrets never appear in logs: `mask()` helpers and `SettingsStore.safe_snapshot()`
guarantee redaction.
"""
from __future__ import annotations

import os
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parent.parent
BACKEND_DIR = Path(__file__).resolve().parent
DATA_DIR = PROJECT_ROOT / "data"
SESSIONS_DIR = DATA_DIR / "sessions"
LOGS_DIR = DATA_DIR / "logs"
FRONTEND_DIR = PROJECT_ROOT / "frontend"

load_dotenv(PROJECT_ROOT / ".env")

for _d in (DATA_DIR, SESSIONS_DIR, LOGS_DIR, LOGS_DIR / "audit"):
    _d.mkdir(parents=True, exist_ok=True)


def _env(name: str, default: str = "") -> str:
    v = os.environ.get(name)
    return v if v not in (None, "") else default


def _env_bool(name: str, default: bool = False) -> bool:
    return _env(name, str(default)).strip().lower() in ("1", "true", "yes", "on")


def _env_int(name: str, default: int) -> int:
    try:
        return int(_env(name, str(default)))
    except ValueError:
        return default


def mask_secret(value: Optional[str]) -> str:
    """Redact a secret for display/logging: sk-ab...wxyz."""
    if not value:
        return ""
    if len(value) <= 8:
        return "*" * len(value)
    return f"{value[:5]}...{value[-4:]}"


class PermissionMode:
    CONFIRM_RISKY = "confirm_risky"   # low risk auto, med/high/critical require approval
    ALLOW_ALL = "allow_all"           # prompts skipped (explicit user opt-in)
    STRICT = "strict"                 # everything requires approval


PERMISSION_MODES = (PermissionMode.CONFIRM_RISKY, PermissionMode.ALLOW_ALL, PermissionMode.STRICT)


@dataclass
class CustomProviderConfig:
    """User-defined OpenAI-compatible provider configured via the settings UI."""
    name: str = ""
    endpoint: str = ""
    api_key: str = ""
    model: str = ""
    headers: dict[str, str] = field(default_factory=dict)

    @property
    def is_configured(self) -> bool:
        return bool(self.endpoint and self.model)

    def safe_dict(self) -> dict:
        return {
            "name": self.name,
            "endpoint": self.endpoint,
            "model": self.model,
            "api_key_masked": mask_secret(self.api_key),
            "has_key": bool(self.api_key),
            "headers": {k: mask_secret(v) if _looks_like_secret(k) else v for k, v in self.headers.items()},
        }


def _looks_like_secret(key: str) -> bool:
    k = key.lower()
    return any(s in k for s in ("key", "token", "secret", "authorization", "auth"))


@dataclass
class OllamaConfig:
    enabled: bool = False
    base_url: str = "http://localhost:11434"
    model: str = ""

    @property
    def is_configured(self) -> bool:
        return bool(self.model)


@dataclass
class RuntimeSettings:
    """Everything the settings UI can change while the server runs."""
    # Provider selection: "openrouter" | "custom" | "ollama"
    active_provider: str = "openrouter"
    # OpenRouter dual keys (never logged in clear)
    openrouter_key_1: str = ""
    openrouter_key_2: str = ""
    # Per-agent model overrides (agent -> model id)
    agent_models: dict[str, str] = field(default_factory=dict)
    # Security
    permission_mode: str = PermissionMode.CONFIRM_RISKY
    # UI
    theme: str = "light"
    # Screen pipeline
    screen_enabled: bool = True
    screen_capture_interval: float = 0.8  # seconds between captures during execution
    screen_max_elements: int = 60
    # Voice
    stt_engine: str = "auto"  # auto | faster_whisper | browser
    whisper_model: str = "base.en"
    # Execution limits
    step_timeout: float = 30.0
    max_steps_per_plan: int = 15
    max_retries_per_step: int = 2
    max_recovery_cycles: int = 2


class Config:
    """Static configuration loaded once from environment variables."""

    def __init__(self) -> None:
        self.host: str = _env("COLUM_HOST", "127.0.0.1")
        self.port: int = _env_int("COLUM_PORT", 8765)
        self.log_level: str = _env("COLUM_LOG_LEVEL", "INFO").upper()
        self.version: str = "1.0.0"
        self.app_name: str = "COLUM"
        self.tesseract_cmd: str = _env("COLUM_TESSERACT_CMD", "")
        self.whisper_model: str = _env("COLUM_WHISPER_MODEL", "base.en")

        # Keys are stored on the runtime settings store (mutable from UI); env seeds them.
        self.openrouter_key_1: str = _env("OPENROUTER_API_1", "")
        self.openrouter_key_2: str = _env("OPENROUTER_API_2", "")

        self.custom_provider = CustomProviderConfig(
            name=_env("CUSTOM_PROVIDER_NAME", ""),
            endpoint=_env("CUSTOM_PROVIDER_ENDPOINT", ""),
            api_key=_env("CUSTOM_PROVIDER_API_KEY", ""),
            model=_env("CUSTOM_PROVIDER_MODEL", ""),
        )
        self.ollama = OllamaConfig(
            enabled=_env_bool("OLLAMA_ENABLED", False),
            base_url=_env("OLLAMA_BASE_URL", "http://localhost:11434"),
            model=_env("OLLAMA_MODEL", ""),
        )

        # Model defaults per micro-agent (documentation examples, all configurable).
        self.default_agent_models: dict[str, str] = {
            "input_analysis": _env("COLUM_MODEL_INPUT_ANALYSIS", "google/gemini-2.0-flash-exp:free"),
            "planner": _env("COLUM_MODEL_PLANNER", "meta-llama/llama-3.3-70b-instruct:free"),
            "tool_call": _env("COLUM_MODEL_TOOL_CALL", "qwen/qwen-2.5-coder-32b-instruct:free"),
            "execution": _env("COLUM_MODEL_EXECUTION", "meta-llama/llama-3.3-70b-instruct:free"),
            "error_handler": _env("COLUM_MODEL_ERROR_HANDLER", "mistralai/mistral-7b-instruct:free"),
            "master": _env("COLUM_MODEL_MASTER", "meta-llama/llama-3.3-70b-instruct:free"),
        }

        self.permission_mode: str = _env("COLUM_PERMISSION_MODE", PermissionMode.CONFIRM_RISKY)

    @property
    def openrouter_base_url(self) -> str:
        return "https://openrouter.ai/api/v1"


config = Config()
settings = RuntimeSettings()

# Seed runtime settings from static config (env values win until user changes them).
settings.openrouter_key_1 = config.openrouter_key_1
settings.openrouter_key_2 = config.openrouter_key_2
settings.permission_mode = config.permission_mode if config.permission_mode in PERMISSION_MODES else PermissionMode.CONFIRM_RISKY
settings.whisper_model = config.whisper_model
settings.agent_models = dict(config.default_agent_models)

_settings_lock = threading.RLock()


def get_settings() -> RuntimeSettings:
    """Return the live runtime settings (mutations must hold the lock)."""
    return settings


def settings_lock() -> threading.RLock:
    return _settings_lock


class SettingsStore:
    """Thread-safe accessor/mutator for runtime settings used by the API layer."""

    def get(self) -> RuntimeSettings:
        with _settings_lock:
            return settings

    def update(self, **kwargs) -> list[str]:
        """Apply a partial update; unknown/invalid fields are rejected. Returns applied keys."""
        allowed = {
            "active_provider", "openrouter_key_1", "openrouter_key_2", "agent_models",
            "permission_mode", "theme", "screen_enabled", "screen_capture_interval",
            "screen_max_elements", "stt_engine", "whisper_model", "step_timeout",
            "max_steps_per_plan", "max_retries_per_step", "max_recovery_cycles",
        }
        applied: list[str] = []
        with _settings_lock:
            for k, v in kwargs.items():
                if k not in allowed or v is None:
                    continue
                if k == "permission_mode" and v not in PERMISSION_MODES:
                    continue
                if k == "active_provider" and v not in ("openrouter", "custom", "ollama"):
                    continue
                if k == "theme" and v not in ("light", "dark"):
                    continue
                if k == "max_steps_per_plan":
                    v = max(1, min(int(v), 30))
                if k in ("step_timeout", "screen_capture_interval"):
                    v = max(1.0, min(float(v), 300.0))
                if k == "screen_max_elements":
                    v = max(5, min(int(v), 200))
                setattr(settings, k, v)
                applied.append(k)
        return applied

    def snapshot(self) -> dict:
        """JSON-safe snapshot with all secrets masked."""
        with _settings_lock:
            return {
                "active_provider": settings.active_provider,
                "openrouter_key_1_masked": mask_secret(settings.openrouter_key_1),
                "openrouter_key_1_set": bool(settings.openrouter_key_1),
                "openrouter_key_2_masked": mask_secret(settings.openrouter_key_2),
                "openrouter_key_2_set": bool(settings.openrouter_key_2),
                "agent_models": dict(settings.agent_models),
                "permission_mode": settings.permission_mode,
                "theme": settings.theme,
                "screen_enabled": settings.screen_enabled,
                "screen_capture_interval": settings.screen_capture_interval,
                "screen_max_elements": settings.screen_max_elements,
                "stt_engine": settings.stt_engine,
                "whisper_model": settings.whisper_model,
                "step_timeout": settings.step_timeout,
                "max_steps_per_plan": settings.max_steps_per_plan,
                "max_retries_per_step": settings.max_retries_per_step,
                "max_recovery_cycles": settings.max_recovery_cycles,
                "custom_provider": config.custom_provider.safe_dict(),
                "ollama": {
                    "enabled": config.ollama.enabled,
                    "base_url": config.ollama.base_url,
                    "model": config.ollama.model,
                },
            }


settings_store = SettingsStore()
