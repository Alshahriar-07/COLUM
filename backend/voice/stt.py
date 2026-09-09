"""Voice/STT — local speech recognition via faster-whisper (optional).

Honesty contract: when faster-whisper or its model is unavailable the engine
reports exactly that; the frontend falls back to the browser Web Speech API.
No fake transcriptions are ever returned.
"""
from __future__ import annotations

import asyncio
import io
import wave
from typing import Any, Optional

from backend.config import get_settings
from backend.logging_utils import get_logger, log_json

log = get_logger("voice")

try:
    from faster_whisper import WhisperModel  # type: ignore
    FASTER_WHISPER_AVAILABLE = True
except Exception:  # pragma: no cover
    FASTER_WHISPER_AVAILABLE = False

MAX_AUDIO_BYTES = 25 * 1024 * 1024  # 25 MB guard
MAX_DURATION_S = 120.0


class STTEngine:
    """Lazy-loading faster-whisper wrapper. Thread-safe probe once."""

    def __init__(self) -> None:
        self._model: Optional[Any] = None
        self._model_name: str = ""
        self._load_failed = False
        self._lock = asyncio.Lock()

    @property
    def available(self) -> bool:
        if not FASTER_WHISPER_AVAILABLE or self._load_failed:
            return False
        return True

    def status(self) -> dict[str, Any]:
        return {
            "engine": "faster_whisper",
            "library_available": FASTER_WHISPER_AVAILABLE,
            "model_loaded": self._model is not None,
            "model_name": self._model_name or get_settings().whisper_model,
            "available": self.available,
            "fallback": "browser_web_speech" if not self.available else None,
        }

    async def _ensure_model(self, model_name: str) -> bool:
        async with self._lock:
            if self._model is not None and self._model_name == model_name:
                return True
            if self._load_failed or not FASTER_WHISPER_AVAILABLE:
                return False
            def _load():
                return WhisperModel(
                    model_name, device="cpu", compute_type="int8")
            try:
                log_json(log, 20, "stt_model_loading", model=model_name)
                self._model = await asyncio.to_thread(_load)
                self._model_name = model_name
                log_json(log, 20, "stt_model_loaded", model=model_name)
                return True
            except Exception as exc:  # noqa: BLE001 - download may be impossible
                self._load_failed = True
                log_json(log, 30, "stt_model_load_failed",
                         model=model_name, error=type(exc).__name__)
                return False

    async def transcribe_wav(self, data: bytes,
                             language: str = "en") -> dict[str, Any]:
        """Transcribe a WAV file payload. Returns honest result dict."""
        if not FASTER_WHISPER_AVAILABLE:
            return {"ok": False, "text": "", "engine": "",
                    "error": "faster-whisper is not installed on this machine"}
        if not data:
            return {"ok": False, "text": "", "engine": "",
                    "error": "empty audio payload"}
        if len(data) > MAX_AUDIO_BYTES:
            return {"ok": False, "text": "", "engine": "",
                    "error": "audio payload too large"}

        model_name = get_settings().whisper_model or "base.en"
        ok = await self._ensure_model(model_name)
        if not ok:
            return {"ok": False, "text": "", "engine": "",
                    "error": ("speech model unavailable "
                              "(download failed or unsupported)")}

        try:
            with wave.open(io.BytesIO(data), "rb") as wf:
                frames = wf.getnframes()
                rate = wf.getframerate()
                duration = frames / float(rate or 1)
        except (wave.Error, EOFError) as exc:
            return {"ok": False, "text": "", "engine": "",
                    "error": f"invalid WAV payload: {type(exc).__name__}"}
        if duration > MAX_DURATION_S:
            return {"ok": False, "text": "", "engine": "",
                    "error": f"audio too long ({duration:.0f}s > {MAX_DURATION_S:.0f}s)"}
        if duration < 0.2:
            return {"ok": True, "text": "", "engine": model_name, "error": None}

        def _run():
            segments, info = self._model.transcribe(
                io.BytesIO(data), language=language, beam_size=2)
            return "".join(s.text for s in segments).strip(), info
        try:
            text, info = await asyncio.to_thread(_run)
        except Exception as exc:  # noqa: BLE001
            log_json(log, 30, "stt_transcribe_failed", error=type(exc).__name__)
            return {"ok": False, "text": "", "engine": model_name,
                    "error": f"transcription failed: {type(exc).__name__}"}
        log_json(log, 20, "stt_transcribed", chars=len(text),
                 duration_s=round(duration, 2), language=info.language)
        return {"ok": True, "text": text[:4000], "engine": model_name,
                "error": None}


stt_engine = STTEngine()
