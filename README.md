# COLUM — computer oparation and logic utility machine

COLUM is a control layer for Windows: an AI that plans, asks permission, and
executes real actions on your computer through validated tools — never raw LLM
output. AI planning and local execution are strictly separated.

![COLUM](assets/banner.png)

## Architecture

```
USER (text / voice)
   ↓
Master Agent  →  MASTPE (5 micro-agents)
   ↓                Input Analysis → Planner → Tool Call → Execution → Error Handling
Structured Plan (JSON, validated)
   ↓
Security: risk classification → validation → permission
   ↓
Tool Registry → Windows (PyAutoGUI / Playwright / subprocess / PyWinAuto / PyMuPDF / BS4)
   ↓
Screen verification → Error handling / replan
   ↓
RESULT (streamed live to the UI)
```

## Quick start

```bash
pip install -r requirements.txt
copy .env.example .env        # fill in OPENROUTER_API_1 / _2
python -m uvicorn backend.main:app --host 127.0.0.1 --port 8765
# open http://127.0.0.1:8765
```

Optional extras:

| Feature | Dependency | Behavior when missing |
|---|---|---|
| OCR / screen verification | [Tesseract](https://github.com/UB-Mannheim/tesseract/wiki) (set `COLUM_TESSERACT_CMD`) | window-level context only, verification honestly reports "cannot verify" |
| Local voice STT | `faster-whisper` (in requirements) | falls back to browser Web Speech API |
| Global hotkey | `keyboard` (in requirements) | UI button + `POST /api/kill` still work |
| Browser automation | `playwright install chromium` | falls back to system Chrome channel |

## Security model

- **No LLM output is ever executed directly.** Plans are parsed into typed
  `PlanStep`s, validated against the tool registry (schema, types, coordinate
  bounds, path traversal, size caps).
- **Risk levels** (LOW/MEDIUM/HIGH/CRITICAL) with argument-aware escalation —
  e.g. a terminal command containing `del`/`format` becomes CRITICAL.
- **Permission flow** with three modes: `confirm_risky` (default), `strict`,
  and `allow_all` (explicit opt-in, visible warning in the UI).
- **Terminal allowlist**: shell=False, command-head allowlist, dangerous-token
  rejection, hard timeout, kill-switch termination.
- **Emergency kill switch: Ctrl + Alt + K** (plus the UI button and
  `POST /api/kill`): cancels tasks, closes the browser, kills subprocesses,
  cancels pending permissions, resets state, preserves sessions, writes a log.
- **Audit trail**: append-only permission log in `data/logs/audit/`, structured
  logs with automatic secret redaction.

## API overview

| Endpoint | Purpose |
|---|---|
| `POST /api/chat` | full pipeline: analyze → plan → execute (or plan only) |
| `POST /api/plan` | plan only, no execution |
| `GET/POST /api/settings` | runtime settings (providers, keys, modes, limits) |
| `GET /api/status` | providers, usage, kill switch, screen, voice |
| `GET/POST /api/permission/*` | pending prompts / decisions |
| `GET /api/screen` | compact screen context JSON |
| `GET /api/session` · `/api/session/{id}` | sessions & restore |
| `POST /api/voice/transcribe` | local STT (WAV payload) |
| `POST /api/kill` · `/api/kill/reset` · `/api/stop` | emergency stop / reset / stop plan |
| `WS /ws/events` | live agent/plan/step/permission event stream |

## Development

```bash
python -m pytest tests/          # 83 tests: security, providers, tools, memory, screen, agents, API
```

Docs: `docs/CURRENT_IMPLEMENTATION_STATUS.md` (subsystem status),
`docs/DEVELOPMENT_PROGRESS.md` (journal), `Project info/` (original spec).
