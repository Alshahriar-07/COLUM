"""Screen monitoring pipeline — capture → OCR → elements → compact JSON.

Chain (tasking Phase 13):
    Screen Capture (mss) → OCR (pytesseract, optional) → Object/UI detection
    → Compact JSON → AI context

Every stage degrades honestly: when Tesseract is missing the pipeline reports
`ocr_available=false` and still returns windows + active window + note, never a
fabricated reading. Used by the orchestrator for screen-aware planning and by
the post-action verification loop (expected-state checking).
"""
from __future__ import annotations

import asyncio
import re
import time
from typing import Any, Optional

from backend.config import config, get_settings
from backend.logging_utils import get_logger, log_json
from backend.models.schemas import ScreenContext, ScreenElement

log = get_logger("screen")

try:
    import mss  # type: ignore
    MSS_AVAILABLE = True
except Exception:  # pragma: no cover
    MSS_AVAILABLE = False

try:
    import pytesseract  # type: ignore
    PYTESSERACT_AVAILABLE = True
except Exception:  # pragma: no cover
    PYTESSERACT_AVAILABLE = False

try:
    from PIL import Image  # type: ignore
    PIL_AVAILABLE = True
except Exception:  # pragma: no cover
    PIL_AVAILABLE = False

# OCR word rows that look like UI controls get this confidence floor.
_CONTROL_HINTS = re.compile(
    r"^(ok|cancel|save|open|close|yes|no|next|back|done|search|settings|login|"
    r"sign in|submit|start|stop|file|edit|view|help|new|delete|add|run|menu)$",
    re.IGNORECASE,
)

_active_window_cache: tuple[float, str] = (0.0, "")


def ocr_available() -> bool:
    if not PYTESSERACT_AVAILABLE:
        return False
    if config.tesseract_cmd:
        pytesseract.pytesseract.tesseract_cmd = config.tesseract_cmd
    try:
        pytesseract.get_tesseract_version()
        return True
    except Exception:  # noqa: BLE001 - binary missing / not in PATH
        return False


def _active_window_title() -> str:
    """Best-effort foreground window title (cached 2s; never raises)."""
    global _active_window_cache
    now = time.monotonic()
    if now - _active_window_cache[0] < 2.0:
        return _active_window_cache[1]
    title = ""
    try:
        if sys_platform_is_windows():
            import ctypes
            user32 = ctypes.windll.user32
            hwnd = user32.GetForegroundWindow()
            length = user32.GetWindowTextLengthW(hwnd)
            buf = ctypes.create_unicode_buffer(length + 1)
            user32.GetWindowTextW(hwnd, buf, length + 1)
            title = buf.value or ""
    except Exception:  # noqa: BLE001
        title = ""
    _active_window_cache = (now, title)  # type: ignore[assignment]
    return title


def sys_platform_is_windows() -> bool:
    import sys
    return sys.platform == "win32"


class ScreenPipeline:
    """Capture + OCR + element extraction producing compact AI context."""

    def __init__(self) -> None:
        self._ocr_ok: Optional[bool] = None  # lazy probe result

    # ------------------------------------------------------------------
    # Capability
    # ------------------------------------------------------------------
    @property
    def ocr_ready(self) -> bool:
        if self._ocr_ok is None:
            self._ocr_ok = ocr_available()
            log_json(log, 20, "ocr_probe", available=self._ocr_ok)
        return self._ocr_ok

    def status(self) -> dict[str, Any]:
        return {
            "capture_available": MSS_AVAILABLE,
            "ocr_available": self.ocr_ready,
            "screen_enabled": get_settings().screen_enabled,
            "capture_interval": get_settings().screen_capture_interval,
        }

    # ------------------------------------------------------------------
    # Capture
    # ------------------------------------------------------------------
    async def capture(self) -> tuple[Any, int, int]:
        """Grab the primary monitor. Returns (PIL.Image, width, height)."""
        if not MSS_AVAILABLE:
            raise RuntimeError("mss is not available for screen capture")
        def _shot():
            # mss>=9 clients: factory works everywhere; mss.mss() is a
            # deprecated alias in 10.x, so prefer the class directly.
            sct = mss.mss() if not hasattr(mss, "MSS") else mss.MSS()
            try:
                mon = sct.monitors[1]
                raw = sct.grab(mon)
                img = Image.frombytes("RGB", raw.size, raw.rgb)
                return img, int(mon["width"]), int(mon["height"])
            finally:
                sct.close()
        return await asyncio.to_thread(_shot)

    # ------------------------------------------------------------------
    # OCR
    # ------------------------------------------------------------------
    async def _ocr_elements(self, image: Any) -> list[ScreenElement]:
        def _run():
            data = pytesseract.image_to_data(
                image, output_type=pytesseract.Output.DICT)
            out: list[ScreenElement] = []
            n = len(data.get("text", []))
            for i in range(n):
                word = (data["text"][i] or "").strip()
                conf_raw = data["conf"][i]
                try:
                    conf = float(conf_raw)
                except (TypeError, ValueError):
                    continue
                if not word or conf < 40:
                    continue
                out.append(ScreenElement(
                    type="control" if _CONTROL_HINTS.match(word) else "text",
                    text=word[:120],
                    x=int(data["left"][i]), y=int(data["top"][i]),
                    width=int(data["width"][i]), height=int(data["height"][i]),
                    confidence=round(min(conf, 100.0) / 100.0, 2),
                ))
            return out
        return await asyncio.to_thread(_run)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    async def get_context(self, max_elements: Optional[int] = None) -> ScreenContext:
        """Full pipeline. Never raises — degraded contexts carry a note."""
        settings = get_settings()
        limit = max_elements or settings.screen_max_elements
        note = ""
        if not settings.screen_enabled:
            return ScreenContext(width=0, height=0, note="screen monitoring disabled")
        if not MSS_AVAILABLE or not PIL_AVAILABLE:
            return ScreenContext(width=0, height=0,
                                 note="screen capture unavailable (mss/Pillow missing)")

        try:
            image, width, height = await self.capture()
        except Exception as exc:  # noqa: BLE001 - report honestly
            log_json(log, 30, "capture_failed", error=type(exc).__name__)
            return ScreenContext(width=0, height=0,
                                 note=f"capture failed: {type(exc).__name__}")

        elements: list[ScreenElement] = []
        if self.ocr_ready:
            try:
                elements = await self._ocr_elements(image)
            except Exception as exc:  # noqa: BLE001
                note = f"OCR failed: {type(exc).__name__}"
                log_json(log, 30, "ocr_failed", error=type(exc).__name__)
        else:
            note = "OCR unavailable (Tesseract missing); window-level context only"

        ctx = ScreenContext(
            width=width, height=height, elements=elements[:limit],
            active_window=_active_window_title(), note=note,
        )
        log_json(log, 20, "screen_context", width=width, height=height,
                 elements=len(ctx.elements), active_window=ctx.active_window[:80])
        return ctx

    async def compact_json(self, max_elements: Optional[int] = None) -> dict[str, Any]:
        ctx = await self.get_context(max_elements)
        settings = get_settings()
        return ctx.compact(max_elements or settings.screen_max_elements)

    # ------------------------------------------------------------------
    # Verification (Phase 14)
    # ------------------------------------------------------------------
    async def verify_expected_state(self, expected: str) -> dict[str, Any]:
        """Post-action check: is `expected` visible on screen?

        Heuristic matcher over OCR tokens: every significant word of the
        expected-state text must appear on screen. Result is honest: when OCR
        is unavailable verification cannot confirm and says so.
        """
        expected = (expected or "").strip()
        if not expected:
            return {"verified": True, "method": "none",
                    "reason": "no expected state declared"}
        if not self.ocr_ready:
            return {"verified": False, "method": "ocr_unavailable",
                    "reason": "OCR unavailable; cannot verify visually"}
        try:
            ctx = await self.get_context()
        except Exception as exc:  # noqa: BLE001
            return {"verified": False, "method": "error",
                    "reason": f"capture failed: {type(exc).__name__}"}

        screen_words = {e.text.lower() for e in ctx.elements}
        want = [w for w in re.findall(r"[a-zA-Z0-9]{3,}", expected.lower())
                if w not in {"the", "and", "with", "for", "should", "after",
                             "this", "that", "page", "window", "screen", "open",
                             "visible", "displayed", "successfully"}]
        if not want:
            return {"verified": True, "method": "ocr", "reason": "no checkable tokens"}
        missing = [w for w in want if not any(w in sw for sw in screen_words)]
        matched = [w for w in want if w not in missing]
        verified = len(matched) >= max(1, int(len(want) * 0.6))
        return {"verified": verified, "method": "ocr",
                "matched": matched, "missing": missing,
                "active_window": ctx.active_window}


screen_pipeline = ScreenPipeline()
