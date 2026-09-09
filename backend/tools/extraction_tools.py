"""Extraction tools — PyMuPDF (PDF) and BeautifulSoup4 (HTML)."""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from backend.logging_utils import get_logger, log_json
from backend.models.schemas import RiskLevel
from backend.tools.base import BaseTool, ExecutionContext, ToolError, ToolSpec

log = get_logger("tools.extraction")

try:
    import pymupdf  # PyMuPDF
    PYMUPDF_AVAILABLE = True
except Exception:  # pragma: no cover
    PYMUPDF_AVAILABLE = False

try:
    from bs4 import BeautifulSoup
    BS4_AVAILABLE = True
except Exception:  # pragma: no cover
    BS4_AVAILABLE = False

MAX_TEXT = 30000
MAX_PAGES = 60
MAX_HTML = 2_000_000


def _safe_path(raw: Any, must_exist: bool = True) -> Path:
    if not isinstance(raw, str) or not raw.strip():
        raise ToolError("path must be a non-empty string")
    p = Path(raw.strip()).expanduser()
    if not p.is_absolute():
        p = Path.cwd() / p
    p = p.resolve()
    if must_exist and not p.exists():
        raise ToolError(f"file not found: {p}")
    if p.exists() and not p.is_file():
        raise ToolError(f"path is not a file: {p}")
    return p


class PdfExtractTool(BaseTool):
    def __init__(self) -> None:
        self.spec = ToolSpec(
            name="pdf.extract",
            description="Extract text and metadata from a PDF file (first N pages).",
            risk=RiskLevel.LOW,
            args_schema={"path": "str", "max_pages": "int"},
            required=("path",), timeout_s=60.0, category="extraction",
        )

    async def run(self, args: dict[str, Any], ctx: ExecutionContext) -> dict[str, Any]:
        ctx.raise_if_cancelled()
        if not PYMUPDF_AVAILABLE:
            raise ToolError("PyMuPDF is not installed (pip install PyMuPDF)")
        path = _safe_path(args["path"])
        if path.suffix.lower() != ".pdf":
            raise ToolError("not a PDF file")
        max_pages = max(1, min(int(args.get("max_pages", 20)), MAX_PAGES))
        # Blocking CPU work → thread
        import asyncio
        return await asyncio.to_thread(self._extract, path, max_pages, ctx)

    def _extract(self, path: Path, max_pages: int, ctx: ExecutionContext) -> dict[str, Any]:
        try:
            doc = pymupdf.open(str(path))
        except Exception as exc:
            raise ToolError(f"could not open PDF: {type(exc).__name__}")
        pages_text: list[dict[str, Any]] = []
        try:
            for i, page in enumerate(doc):
                if i >= max_pages:
                    break
                ctx.raise_if_cancelled()
                pages_text.append({
                    "page": i + 1,
                    "text": page.get_text("text")[:MAX_TEXT // max_pages],
                })
            meta = doc.metadata or {}
        finally:
            doc.close()
        combined = "\n\n".join(p["text"] for p in pages_text)[:MAX_TEXT]
        log_json(log, 20, "pdf_extracted", pages=len(pages_text), path_name=path.name)
        return {
            "file": path.name,
            "page_count": len(pages_text),
            "pages": pages_text,
            "text": combined,
            "metadata": {k: str(v) for k, v in meta.items() if v},
        }


class WebParseTool(BaseTool):
    def __init__(self) -> None:
        self.spec = ToolSpec(
            name="web.parse",
            description="Parse an HTML string and extract title, headings, links and text.",
            risk=RiskLevel.LOW,
            args_schema={"html": "str"}, required=("html",),
            timeout_s=30.0, category="extraction",
        )

    async def run(self, args: dict[str, Any], ctx: ExecutionContext) -> dict[str, Any]:
        ctx.raise_if_cancelled()
        if not BS4_AVAILABLE:
            raise ToolError("BeautifulSoup4 is not installed")
        html = args.get("html")
        if not isinstance(html, str) or not html.strip():
            raise ToolError("html must be a non-empty string")
        if len(html) > MAX_HTML:
            raise ToolError("html payload too large")
        import asyncio
        return await asyncio.to_thread(self._parse, html)

    def _parse(self, html: str) -> dict[str, Any]:
        soup = BeautifulSoup(html, "lxml" if BS4_AVAILABLE else "html.parser")
        for tag in soup(["script", "style", "noscript"]):
            tag.decompose()
        title = (soup.title.string if soup.title else "") or ""
        headings = [
            {"level": h.name, "text": h.get_text(strip=True)[:200]}
            for h in soup.find_all(["h1", "h2", "h3"])[:30]
        ]
        links = []
        for a in soup.find_all("a", href=True)[:60]:
            links.append({"text": a.get_text(strip=True)[:120], "href": a["href"][:500]})
        text = re.sub(r"\n{3,}", "\n\n", soup.get_text("\n", strip=True))[:MAX_TEXT]
        log_json(log, 20, "web_parsed", links=len(links), headings=len(headings))
        return {"title": title.strip()[:300], "headings": headings,
                "links": links, "text": text}


pdf_tool = PdfExtractTool()
web_parser = WebParseTool()


def register_extraction_tools(reg) -> None:
    reg.register(pdf_tool)
    reg.register(web_parser)
    log_json(log, 20, "extraction_tools_registered", count=2,
             pymupdf=PYMUPDF_AVAILABLE, bs4=BS4_AVAILABLE)
