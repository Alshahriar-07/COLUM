"""Configuration loader for COLUM."""

import os
from pathlib import Path
from typing import Any, Dict, Optional

import yaml
from dotenv import load_dotenv


class Config:
    """Application configuration with environment variable overrides."""

    def __init__(self, config_path: Optional[str] = None):
        self._config: Dict[str, Any] = {}
        self._load_config(config_path)

    def _load_config(self, config_path: Optional[str]) -> None:
        load_dotenv()

        if config_path is None:
            config_path = os.environ.get("COLUM_CONFIG", "config.yaml")

        path = Path(config_path)
        if path.exists():
            with open(path, "r", encoding="utf-8") as f:
                self._config = yaml.safe_load(f) or {}
        else:
            self._config = {}

        self._apply_env_overrides()

    def _apply_env_overrides(self) -> None:
        env_mappings = {
            "OPENROUTER_API_KEY": ("openrouter", "api_key"),
            "OPENROUTER_MODE": ("openrouter", "mode"),
            "OPENROUTER_MODEL": ("openrouter", "specific_model"),
            "OPENROUTER_FALLBACK_ENABLED": ("openrouter", "fallback_enabled"),
            "COLUM_NAME": ("assistant", "name"),
            "COLUM_WAKE_WORD": ("assistant", "wake_word"),
            "COLUM_INACTIVITY_TIMEOUT_MINUTES": ("assistant", "inactivity_timeout_minutes"),
            "VOICE_STT_PROVIDER": ("voice", "stt_provider"),
            "VOICE_TTS_PROVIDER": ("voice", "tts_provider"),
            "VOICE_PUSH_TO_TALK_ENABLED": ("voice", "push_to_talk_enabled"),
            "VOICE_LANGUAGE": ("voice", "language"),
            "VISION_ENABLED": ("vision", "enabled"),
            "VISION_CAPTURE_MODE": ("vision", "capture_mode"),
            "SECURITY_CONFIRMATION_MODE": ("security", "confirmation_mode"),
            "SECURITY_ALLOW_FILE_DELETE": ("security", "allow_file_delete"),
            "SECURITY_ALLOW_EXTERNAL_SEND": ("security", "allow_external_send"),
            "SECURITY_ALLOW_ADMIN_COMMANDS": ("security", "allow_admin_commands"),
            "MEMORY_ENABLED": ("memory", "enabled"),
            "MEMORY_STORE_RAW_AUDIO": ("memory", "store_raw_audio"),
            "MEMORY_STORE_RAW_SCREENSHOTS": ("memory", "store_raw_screenshots"),
            "WORKSPACE_DEFAULT": ("workspace", "default"),
            "LOG_LEVEL": ("logging", "level"),
            "LOG_FILE": ("logging", "file"),
            "UI_THEME": ("ui", "theme"),
            "UI_ANIMATIONS_ENABLED": ("ui", "animations_enabled"),
            "BACKEND_HOST": ("server", "host"),
            "BACKEND_PORT": ("server", "http_port"),
            "BACKEND_WS_PORT": ("server", "ws_port"),
        }

        for env_var, (section, key) in env_mappings.items():
            value = os.environ.get(env_var)
            if value is not None:
                self._set_nested(section, key, self._parse_value(value))

    def _set_nested(self, section: str, key: str, value: Any) -> None:
        if section not in self._config:
            self._config[section] = {}
        self._config[section][key] = value

    def _parse_value(self, value: str) -> Any:
        if value.lower() in ("true", "false"):
            return value.lower() == "true"
        try:
            if "." in value:
                return float(value)
            return int(value)
        except ValueError:
            return value

    def get(self, section: str, key: str, default: Any = None) -> Any:
        return self._config.get(section, {}).get(key, default)

    def get_section(self, section: str) -> Dict[str, Any]:
        return self._config.get(section, {})

    def get_all(self) -> Dict[str, Any]:
        return self._config.copy()

    def reload(self, config_path: Optional[str] = None) -> None:
        self._load_config(config_path)


_config_instance: Optional[Config] = None


def get_config(config_path: Optional[str] = None) -> Config:
    global _config_instance
    if _config_instance is None:
        _config_instance = Config(config_path)
    return _config_instance


def reset_config() -> None:
    global _config_instance
    _config_instance = None