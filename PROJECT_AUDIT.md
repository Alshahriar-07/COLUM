# COLUM — Project Audit (Phase 1)

Date: 2026-09-09
Auditor: Lead engineer (pre-implementation audit)

## 1. Repository State

| Path | Contents |
|---|---|
| `Project info/` | 26 Markdown documentation files (source-of-truth spec, derived from `COLUM PLAN CHART.docx`) |
| `assets/` | 18 branding files: `icon.ico`, `icon.png` + sizes 16–1024, `icon.svg`, `icon-dark.png`, `icon-transparent.png`, `wordmark.png`, `banner.png`, `banner-dark.png`, `favicon.png`, `README.md` |
| `frontend/`, `backend/`, `tests/`, `data/`, `docs/` | **Did not exist** — created as empty scaffolding during this audit |

**Conclusion: this is a greenfield implementation.** No existing frontend code, backend code, configuration, dependencies, or tests exist. Nothing is broken because nothing is implemented. The documentation package and branding assets are complete and high quality.

## 2. Existing Assets (preserved, never regenerated)

All branding is supplied and consistent: squircle robot icon (multi-size PNG + ICO + SVG), light/dark banners, wordmark, favicon. Per asset policy these files are **used as-is**; copies were made into `frontend/assets/` for web serving, originals untouched.

## 3. Source-of-Truth Requirements Extracted

From the documentation package:

- **Concept:** COLUM is a control layer/environment, not an AI model. AI planning and local execution must stay separated.
- **Stack:** HTML/CSS/JS frontend, Python + FastAPI backend.
- **Orchestration:** Master Agent → MASTPE → 5 Micro-Agents (Input Analysis, Planner, Tool Call, Execution, Error Handling), parallel analysis, structured plan format, never raw LLM output execution.
- **Providers:** OpenRouter (dual-key failover: `OPENROUTER_API_1` primary, `OPENROUTER_API_2` fallback), custom provider (name/endpoint/key/model/headers), local Ollama. Provider code behind a common adapter interface. Models configurable, never hard-coded.
- **Tools:** PyAutoGUI, Playwright, subprocess (HIGH RISK), PyMuPDF, BeautifulSoup4, PyWinAuto — each behind validated adapters and a centralized tool registry.
- **Security:** risk levels (LOW/MEDIUM/HIGH/CRITICAL), permission flow, allow-all mode (explicit, visible), kill switch Ctrl+Alt+K (independent listener), validation, timeouts, cancellation, audit logs.
- **Screen:** capture → OCR → detection → element extraction → compact JSON → agent context; post-action verification loop.
- **Voice:** local STT (Faster-Whisper/whisper.cpp preferred), floating overlay with waveform, integrated pipeline.
- **Memory:** compact JSON session summaries in `data/sessions/`, latest-session restore on startup, no secrets stored.
- **UI:** neumorphism (base #E0E5EC, highlight #FFFFFF, shadow #A3B1C6, text #0D0D0D, dark #1E222B; status green/amber/blue/red), Orbitron + Inter (+ Plus Jakarta Sans), three columns 20/55/25, left sidebar (branding, sessions, usage, settings, about), center (chat, command bar, voice overlay, terminal drawer), right (MASTPE monitor, 5 agent cards, plan roadmap).
- **API areas:** `/api/chat`, `/api/plan`, `/api/execute`, `/api/permission`, `/api/screen`, `/api/session`, `/api/settings`, `/api/status`, `/api/kill` (recommended names, adaptable).
- **Live updates:** WebSocket/SSE streaming of execution lifecycle.
- **Testing:** unit/integration/safety/UI/provider-failure coverage.

## 4. Environment Audit (this machine)

- OS: Windows (bash shell available). Python 3.10.11 (`python`) and 3.12.10 (`python3`) installed.
- **Already installed:** fastapi, uvicorn, pydantic, pydantic-settings, pyautogui, mss, Pillow, beautifulsoup4, httpx, playwright, python-dotenv, pytest.
- **Missing:** PyMuPDF (`fitz`), pywinauto, keyboard, pytesseract, faster-whisper.
- Chrome installed (Playwright can target the system Chrome channel if browser downloads are unavailable).

### Dependency risk notes

| Dependency | Risk / Mitigation |
|---|---|
| `keyboard` (global hotkey hook) | Requires admin on some setups; kill switch must degrade gracefully and the UI emergency-stop button must remain fully functional without it. Documented in SECURITY.md/TROUBLESHOOTING.md. |
| `pytesseract` | Needs the external Tesseract binary. Implemented as an optional OCR backend with capability probing; screen pipeline reports degraded-but-honest status when absent. |
| `faster-whisper` | Large model downloads. Implemented as optional; STT endpoints return a clear "engine unavailable" state rather than pretending to work. Browser Web Speech API used as a frontend-side fallback. |
| `pywinauto` | Windows-only (fine for this project); wrapped defensively so import failure never crashes the backend. |
| `PyMuPDF` | Pure pip install; required for PDF tool. |

## 5. Technical Risks

1. **No API keys present** — OpenRouter features cannot be live-verified without user keys. Architecture + failover implemented and unit-tested with stubbed transports; live verification requires the user to fill `.env`.
2. **Tesseract/STT model availability** — handled via capability detection and honest degraded states (Rule 11: never pretend unavailable functionality works).
3. **`keyboard` global hook privileges** — kill switch implemented in a dedicated daemon thread plus a backend-independent browser-side listener and API endpoint (`/api/kill`), so the guarantee does not rest on a single mechanism.
4. **PyAutoGUI failsafe** — kept enabled (`FAILSAFE=True`): corner-abort remains a second independent emergency mechanism.
5. **Free OpenRouter models are rate-limited/variable** — strict timeouts, bounded retries with backoff, dual-key failover, and a hard fallback chain (OpenRouter → custom → Ollama when enabled).

## 6. Implementation Plan

Follows the phased plan in the tasking, mapped onto the documentation roadmap:

1. Scaffolding: root config files, `data/` dirs, package layout.
2. Backend foundation: `config.py` (env + runtime settings), structured logging, Pydantic schemas, FastAPI app with health/status endpoints and static frontend serving.
3. Provider abstraction: `base.py` interface, OpenRouter adapter with dual-key failover + backoff, custom OpenAI-compatible adapter, Ollama adapter, router with chain fallback.
4. MASTPE: Master Agent + 5 Micro-Agents, JSON-mode structured plan, validation/reconciliation, event bus.
5. Security engine: risk classifier, action validator, tool allowlist, permission manager (incl. allow-all), execution limits, audit log, kill switch (thread + listener + API).
6. Tool registry + adapters: pyautogui, playwright, terminal (subprocess), pdf (PyMuPDF), web parser (bs4), pywinauto — each with schema validation, timeouts, cancellation.
7. Screen pipeline: mss capture, OCR (pytesseract if present), element extraction, compact JSON serializer, verification service.
8. Voice: faster-whisper engine (optional, capability-probed), record/transcribe endpoints, overlay in frontend.
9. Memory: session store, summaries, restore-on-startup, corruption handling.
10. Frontend: full neumorphic three-column UI, WebSocket live monitor, terminal drawer, permission dialogs, settings, voice overlay, kill switch.
11. Tests: pytest suite across API, security, tools, memory, screen, providers, agents.
12. Docs + audit + final integration verification.

## 7. Decisions Locked (from docs, not invented)

- Endpoint names as recommended in doc 04 (adapted where architecture requires).
- Risk-level semantics per tasking Phase 9 (LOW/MEDIUM/HIGH/CRITICAL with the given examples).
- Models per agent are **defaults only**, fully configurable via settings/env.
- Session JSON schema finalized at implementation time (doc 10 explicitly permits this).
- Kill switch behavior list (10 items) from tasking Phase 10.
