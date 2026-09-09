"""Playwright adapter — DOM-first browser automation.

Maintains a lazily-launched browser process (Chromium or system Chrome when
available). All actions are DOM-based: clicking uses CSS selectors, never raw
screen coordinates, when possible. The browser is shut down by the kill switch
and at app shutdown. Every action is cancellation-checked.
"""
from __future__ import annotations

import asyncio
from typing import Any, Optional

from backend.events import event_bus
from backend.logging_utils import get_logger, log_json
from backend.models.schemas import RiskLevel
from backend.tools.base import BaseTool, ExecutionContext, ToolError, ToolSpec
from backend.tools.kill_switch_ref import kill_state

log = get_logger("tools.playwright")

try:
    from playwright.async_api import async_playwright, Browser, BrowserContext, Page
    PLAYWRIGHT_AVAILABLE = True
except Exception:  # pragma: no cover
    PLAYWRIGHT_AVAILABLE = False

MAX_TEXT_EXTRACT = 20000
DEFAULT_NAV_TIMEOUT_MS = 30000
MAX_SELECTOR_LEN = 500


class BrowserSession:
    """Owns the playwright browser lifecycle. One session per backend."""

    def __init__(self) -> None:
        self._pw = None
        self._browser: Optional[Browser] = None
        self._context: Optional[BrowserContext] = None
        self._page: Optional[Page] = None
        self._lock = asyncio.Lock()

    async def page(self) -> Page:
        async with self._lock:
            if not PLAYWRIGHT_AVAILABLE:
                raise ToolError(
                    "Playwright is not installed. Run: pip install playwright "
                    "&& python -m playwright install chromium"
                )
            if self._page is None or self._page.is_closed():
                await self._ensure_browser()
            return self._page

    async def _ensure_browser(self) -> None:
        if self._browser is not None and self._browser.is_connected():
            return
        self._pw = await async_playwright().start()
        browser_kwargs: dict[str, Any] = {"headless": False}
        try:
            self._browser = await self._pw.chromium.launch(**browser_kwargs)
        except Exception:
            # Fall back to the system Chrome channel (no browser binaries needed).
            self._browser = await self._pw.chromium.launch(channel="chrome", **browser_kwargs)
        self._context = await self._browser.new_context(viewport=None)
        self._page = await self._context.new_page()
        log_json(log, 20, "browser_launched", engine="chromium")

    @property
    def is_running(self) -> bool:
        return self._browser is not None and self._browser.is_connected()

    async def shutdown(self) -> None:
        async with self._lock:
            try:
                if self._browser is not None:
                    await self._browser.close()
            except Exception:
                pass
            try:
                if self._pw is not None:
                    await self._pw.stop()
            except Exception:
                pass
            self._browser = None
            self._context = None
            self._page = None
            log_json(log, 20, "browser_closed")


browser_session = BrowserSession()


def _check(ctx: ExecutionContext) -> None:
    ctx.raise_if_cancelled()
    if kill_state.is_cancelled():
        ctx.raise_if_cancelled()


def _valid_selector(sel: Any) -> str:
    if not isinstance(sel, str) or not sel.strip():
        raise ToolError("selector must be a non-empty string")
    if len(sel) > MAX_SELECTOR_LEN:
        raise ToolError("selector too long")
    for bad in ("..", "```"):
        if bad in sel:
            raise ToolError(f"invalid characters in selector: {sel!r}")
    return sel.strip()


def _valid_url(url: Any) -> str:
    if not isinstance(url, str) or not url.strip():
        raise ToolError("url must be a non-empty string")
    u = url.strip()
    if not (u.startswith("http://") or u.startswith("https://") or u.startswith("about:")):
        raise ToolError("only http://, https:// and about: URLs are allowed")
    if len(u) > 2000:
        raise ToolError("url too long")
    return u


class _PlaywrightBase(BaseTool):
    def _pre(self, ctx: ExecutionContext) -> None:
        _check(ctx)


class BrowserOpenTool(_PlaywrightBase):
    def __init__(self) -> None:
        self.spec = ToolSpec(
            name="browser.open", description="Launch the automated browser.",
            risk=RiskLevel.MEDIUM, args_schema={}, timeout_s=60.0, category="browser",
        )

    async def run(self, args: dict[str, Any], ctx: ExecutionContext) -> dict[str, Any]:
        self._pre(ctx)
        page = await browser_session.page()
        _check(ctx)
        return {"browser_open": True, "url": page.url}


class BrowserNavigateTool(_PlaywrightBase):
    def __init__(self) -> None:
        self.spec = ToolSpec(
            name="browser.navigate", description="Navigate the browser to a URL.",
            risk=RiskLevel.MEDIUM, args_schema={"url": "str"}, required=("url",),
            timeout_s=60.0, category="browser",
        )

    async def run(self, args: dict[str, Any], ctx: ExecutionContext) -> dict[str, Any]:
        self._pre(ctx)
        url = _valid_url(args["url"])
        page = await browser_session.page()
        try:
            resp = await page.goto(url, timeout=DEFAULT_NAV_TIMEOUT_MS, wait_until="domcontentloaded")
        except Exception as exc:
            raise ToolError(f"navigation failed: {type(exc).__name__}")
        _check(ctx)
        title = await page.title()
        return {"url": page.url, "status": resp.status if resp else 0, "title": title}


class BrowserExtractTool(_PlaywrightBase):
    def __init__(self) -> None:
        self.spec = ToolSpec(
            name="browser.extract",
            description="Extract visible text, title, URL and interactive elements from the page.",
            risk=RiskLevel.LOW, args_schema={"selector": "str"}, timeout_s=30.0,
            category="browser",
        )

    async def run(self, args: dict[str, Any], ctx: ExecutionContext) -> dict[str, Any]:
        self._pre(ctx)
        page = await browser_session.page()
        selector = _valid_selector(args["selector"]) if args.get("selector") else "body"
        try:
            text = await page.locator(selector).inner_text(timeout=8000)
        except Exception as exc:
            raise ToolError(f"extraction failed for selector {selector!r}: {type(exc).__name__}")
        _check(ctx)
        elements = await _interactive_elements(page)
        return {
            "url": page.url,
            "title": await page.title(),
            "text": text[:MAX_TEXT_EXTRACT],
            "elements": elements,
        }


class BrowserClickTool(_PlaywrightBase):
    def __init__(self) -> None:
        self.spec = ToolSpec(
            name="browser.click", description="Click an element identified by a CSS selector.",
            risk=RiskLevel.MEDIUM, args_schema={"selector": "str"}, required=("selector",),
            timeout_s=30.0, category="browser",
        )

    async def run(self, args: dict[str, Any], ctx: ExecutionContext) -> dict[str, Any]:
        self._pre(ctx)
        sel = _valid_selector(args["selector"])
        page = await browser_session.page()
        locator = page.locator(sel).first
        try:
            await locator.wait_for(state="visible", timeout=8000)
            await locator.click(timeout=8000)
        except Exception as exc:
            raise ToolError(f"click failed for selector {sel!r}: {type(exc).__name__}")
        _check(ctx)
        await asyncio.sleep(0.4)  # allow navigation/JS to settle
        return {"clicked": sel, "url": page.url}


class BrowserTypeTool(_PlaywrightBase):
    def __init__(self) -> None:
        self.spec = ToolSpec(
            name="browser.type",
            description="Type text into an input identified by a CSS selector (optionally clearing it first).",
            risk=RiskLevel.MEDIUM, args_schema={"selector": "str", "text": "str", "clear": "bool"},
            required=("selector", "text"), timeout_s=30.0, category="browser",
        )

    async def run(self, args: dict[str, Any], ctx: ExecutionContext) -> dict[str, Any]:
        self._pre(ctx)
        sel = _valid_selector(args["selector"])
        text = str(args.get("text", ""))
        if len(text) > MAX_TEXT_EXTRACT:
            raise ToolError("text too long")
        clear = bool(args.get("clear", True))
        page = await browser_session.page()
        locator = page.locator(sel).first
        try:
            await locator.wait_for(state="visible", timeout=8000)
            if clear:
                await locator.fill("")
            await locator.type(text, timeout=8000)
        except Exception as exc:
            raise ToolError(f"typing failed for selector {sel!r}: {type(exc).__name__}")
        _check(ctx)
        return {"typed_into": sel, "chars": len(text)}


class BrowserFillFormTool(_PlaywrightBase):
    def __init__(self) -> None:
        self.spec = ToolSpec(
            name="browser.fill_form",
            description="Fill multiple form fields: fields is a list of {selector, text} objects.",
            risk=RiskLevel.MEDIUM, args_schema={"fields": "list"}, required=("fields",),
            timeout_s=60.0, category="browser",
        )

    async def run(self, args: dict[str, Any], ctx: ExecutionContext) -> dict[str, Any]:
        self._pre(ctx)
        fields = args.get("fields")
        if not isinstance(fields, list) or not fields or len(fields) > 30:
            raise ToolError("fields must be a non-empty list (max 30)")
        page = await browser_session.page()
        filled: list[dict[str, Any]] = []
        for f in fields:
            _check(ctx)
            if not isinstance(f, dict):
                raise ToolError("each field must be an object with selector/text")
            sel = _valid_selector(f.get("selector", ""))
            text = str(f.get("text", ""))
            locator = page.locator(sel).first
            try:
                await locator.wait_for(state="visible", timeout=8000)
                await locator.fill(text, timeout=8000)
            except Exception as exc:
                raise ToolError(f"fill failed for selector {sel!r}: {type(exc).__name__}")
            filled.append({"selector": sel, "chars": len(text)})
        return {"filled": filled}


class BrowserStateTool(_PlaywrightBase):
    def __init__(self) -> None:
        self.spec = ToolSpec(
            name="browser.state",
            description="Inspect current page state: URL, title, readiness, element counts.",
            risk=RiskLevel.LOW, args_schema={}, timeout_s=15.0, category="browser",
        )

    async def run(self, args: dict[str, Any], ctx: ExecutionContext) -> dict[str, Any]:
        self._pre(ctx)
        if not browser_session.is_running:
            return {"browser_running": False}
        page = await browser_session.page()
        _check(ctx)
        return {
            "browser_running": True,
            "url": page.url,
            "title": await page.title(),
            "links": await page.locator("a").count(),
            "inputs": await page.locator("input, textarea, select").count(),
            "buttons": await page.locator("button, [role=button]").count(),
        }


class BrowserCloseTool(_PlaywrightBase):
    def __init__(self) -> None:
        self.spec = ToolSpec(
            name="browser.close", description="Close the automated browser.",
            risk=RiskLevel.LOW, args_schema={}, timeout_s=20.0, category="browser",
        )

    async def run(self, args: dict[str, Any], ctx: ExecutionContext) -> dict[str, Any]:
        self._pre(ctx)
        await browser_session.shutdown()
        return {"browser_open": False}


async def _interactive_elements(page: Page, limit: int = 50) -> list[dict[str, Any]]:
    """Collect visible interactive elements (DOM-first context for the AI)."""
    js = """
    () => {
      const nodes = document.querySelectorAll(
        'a, button, input, textarea, select, [role="button"], [role="link"]');
      const out = [];
      for (const el of nodes) {
        const r = el.getBoundingClientRect();
        if (r.width < 2 || r.height < 2) continue;
        const style = getComputedStyle(el);
        if (style.visibility === 'hidden' || style.display === 'none') continue;
        out.push({
          type: el.tagName.toLowerCase() === 'a' ? 'link'
              : el.tagName.toLowerCase() === 'button' ? 'button'
              : el.tagName.toLowerCase() === 'input' ? 'input'
              : el.tagName.toLowerCase() === 'textarea' ? 'textarea'
              : el.tagName.toLowerCase() === 'select' ? 'select' : 'element',
          text: (el.innerText || el.value || el.placeholder ||
                 el.getAttribute('aria-label') || '').slice(0, 120),
          selector_hint: el.id ? '#' + el.id
            : el.getAttribute('name') ? '[name="' + el.getAttribute('name') + '"]' : '',
          x: Math.round(r.x), y: Math.round(r.y),
          width: Math.round(r.width), height: Math.round(r.height),
        });
        if (out.length >= 60) break;
      }
      return out;
    }"""
    try:
        raw = await page.evaluate(js)
    except Exception:
        return []
    return raw[:limit]


def register_playwright_tools(reg) -> None:
    reg.register(BrowserOpenTool())
    reg.register(BrowserNavigateTool())
    reg.register(BrowserExtractTool())
    reg.register(BrowserClickTool())
    reg.register(BrowserTypeTool())
    reg.register(BrowserFillFormTool())
    reg.register(BrowserStateTool())
    reg.register(BrowserCloseTool())
    log_json(log, 20, "playwright_tools_registered", count=8, available=PLAYWRIGHT_AVAILABLE)
