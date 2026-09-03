
<div align="center">

<img src="assets/banner.png" alt="COLUM Banner" width="100%">

# COLUM

### Computer Operating & Logic Utility Machine

**An AI desktop assistant and intelligent control layer for Windows.**

<br>

<img src="assets/icon-128.png" alt="COLUM Icon" width="96">

<br><br>

[![Beta](https://img.shields.io/badge/COLUM-Beta%201-000?style=for-the-badge)](https://github.com/Alshahriar-07/COLUM)
[![Windows](https://img.shields.io/badge/Windows-10%20%2F%2011-000?style=for-the-badge&logo=windows&logoColor=white)](https://www.microsoft.com/windows)
[![Python](https://img.shields.io/badge/Python-3.10%2B-000?style=for-the-badge&logo=python&logoColor=white)](https://www.python.org/)
[![Frontend](https://img.shields.io/badge/Frontend-HTML%20%2F%20CSS%20%2F%20JS-000?style=for-the-badge)](https://developer.mozilla.org/)
[![License](https://img.shields.io/badge/License-MIT-000?style=for-the-badge)](#license)

<br>

> **Understand. Plan. Control.**

COLUM is an AI-powered desktop assistant that understands natural language, reasons about tasks, safely executes approved actions, talks through voice or text, and acts as an intelligent control layer for Windows.

</div>

---

## Table of Contents

- [What is COLUM?](#what-is-colum)
- [Why COLUM?](#why-colum)
- [Design Philosophy](#design-philosophy)
- [Beta 1 Goals](#beta-1-goals)
- [Architecture](#architecture)
- [Core Components](#core-components)
- [Security Model](#security-model)
- [Command Lifecycle](#command-lifecycle)
- [OpenRouter Integration](#openrouter-integration)
- [Voice System](#voice-system)
- [Web & Desktop Automation](#web--desktop-automation)
- [Memory System](#memory-system)
- [Frontend & Dashboard](#frontend--dashboard)
- [Project Structure](#project-structure)
- [Installation](#installation)
- [Running COLUM](#running-colum)
- [Configuration](#configuration)
- [Example Commands](#example-commands)
- [HTTP & WebSocket](#http--websocket)
- [Logging & Testing](#logging--testing)
- [Code Quality](#code-quality)
- [Roadmap](#roadmap)
- [Beta 1 Documentation](#beta-1-documentation)
- [Branding & Assets](#branding--assets)
- [Current Status](#current-status)
- [Security Notice](#security-notice)
- [Future Vision](#future-vision)
- [Contributing](#contributing)
- [License](#license)
- [Support](#support)

---

## What is COLUM?

**COLUM** = **Computer Operating & Logic Utility Machine**

Inspired by JARVIS, COLUM is not just a chatbot. It's a complete **AI operating and control layer** for your computer that can:

- Understand natural language
- Reason about your intent
- Break complex requests into tasks
- Choose the right tools for the job
- Ask for confirmation when needed
- Execute desktop operations safely
- Control applications, files, and windows
- Perform web tasks
- Respond by voice or text
- Remember context across sessions

The LLM never touches your operating system directly. Every action goes through a structured pipeline.

---

## Why COLUM?

Most AI assistants live inside a chat box. COLUM bridges:

```
AI  +  Desktop  +  Automation  +  Voice  +  Memory  +  Security
```

into one modular system.

**Example request:**
> *"Open Chrome and search YouTube for Python tutorials."*

**COLUM does this:**
1. Understand the request
2. Build an execution plan
3. Pick the right tools
4. Validate parameters
5. Execute approved actions
6. Verify the result
7. Reply in natural language

**More complex request:**
> *"Organize today's screenshots into a folder."*

1. Detect today's date
2. Find screenshot files
3. Create the destination folder
4. Ask for confirmation if needed
5. Move approved files
6. Verify and report

---

## Design Philosophy

Every request flows through one pipeline:

```
Understand
    ↓
Reason
    ↓
Plan
    ↓
Validate
    ↓
Confirm
    ↓
Execute
    ↓
Verify
    ↓
Report
```

- **LLM** → reasons and plans
- **Local runtime** → enforces security and executes

This separation is the most important principle of the project.

---

## Beta 1 Goals

Beta 1 builds the production-ready foundation:

- Core application architecture
- Python backend
- Configuration management
- Logging
- HTTP server
- WebSocket communication
- HTML / CSS / JS dashboard
- OpenRouter integration
- AI model management
- Tool, security, memory, voice, automation architectures
- Testing foundation
- Full project documentation

Beta 1 deliberately avoids training a custom model. OpenRouter is the initial inference layer.

---

## Architecture

```
                           ┌─────────────────────────┐
                           │       USER / VOICE      │
                           └────────────┬────────────┘
                                        │
                                        ▼
                           ┌─────────────────────────┐
                           │      COLUM FRONTEND     │
                           │       HTML/CSS/JS       │
                           └────────────┬────────────┘
                                        │
                              HTTP / WebSocket
                                        │
                                        ▼
                           ┌─────────────────────────┐
                           │       COLUM CORE        │
                           │ Lifecycle + Event Bus   │
                           └────────────┬────────────┘
                                        │
        ┌───────────────────────────────┼───────────────────────────────┐
        │                               │                               │
        ▼                               ▼                               ▼
┌───────────────┐              ┌───────────────┐              ┌───────────────┐
│   AI LAYER    │              │  AUTOMATION   │              │    MEMORY     │
│  OpenRouter   │              │   Execution   │              │ Context/State │
│ Model Manager │              │   Planning    │              │ Preferences   │
└───────┬───────┘              └───────┬───────┘              └───────────────┘
        │                              │
        └──────────────┬───────────────┘
                       │
                       ▼
              ┌─────────────────┐
              │   TOOL SYSTEM   │
              │  Validation     │
              │  Permissions    │
              │  Execution      │
              └────────┬────────┘
                       │
        ┌──────────────┼──────────────┐
        │              │              │
        ▼              ▼              ▼
┌──────────────┐ ┌──────────────┐ ┌──────────────┐
│   DESKTOP    │ │     WEB      │ │    VOICE     │
│   CONTROL    │ │ AUTOMATION   │ │   STT / TTS  │
└──────────────┘ └──────────────┘ └──────────────┘
```

---

## Core Components

### AI Layer
Handles OpenRouter communication, model selection, fallback, prompt construction, reasoning, planning, tool selection, structured tool calls, and streaming. It never executes OS actions directly.

### Core Runtime
The central infrastructure: lifecycle, startup/shutdown, events, internal communication, HTTP and WebSocket servers, runtime state, error handling, logging integration.

### Tool System
The bridge between AI reasoning and the real system.

```
AI Decision
     ↓
Tool Request
     ↓
Schema Validation
     ↓
Permission Check
     ↓
Risk Assessment
     ↓
Execution
     ↓
Result
```

Planned tools: application launcher, file manager, window manager, keyboard, mouse, screenshot, system info, browser automation, web search, controlled terminal.

---

## Security Model

The AI never gets unrestricted OS access. Every action passes through a risk pipeline:

```
AI Tool Request
        ↓
Parameter Validation
        ↓
Permission Check
        ↓
Risk Classifier
        ↓
   LOW  |  MEDIUM  |  HIGH
   ↓         ↓         ↓
Execute   Policy    Confirmation
                    ↓
              User Approval
                    ↓
                  Execute
```

**Principles**
- No unrestricted LLM shell access
- Structured tool execution
- Parameter validation
- Permission-aware actions
- High-risk confirmation
- API keys never logged
- Sensitive data kept out of prompts when possible
- All actions are auditable

---

## Command Lifecycle

```
┌──────────────────────┐
│      User Input      │
└──────────┬───────────┘
           ▼
┌──────────────────────┐
│  Input Normalization │
└──────────┬───────────┘
           ▼
┌──────────────────────┐
│    Intent Analysis   │
└──────────┬───────────┘
           ▼
┌──────────────────────┐
│  AI Reasoning/Plan   │
└──────────┬───────────┘
           ▼
┌──────────────────────┐
│    Tool Selection    │
└──────────┬───────────┘
           ▼
┌──────────────────────┐
│ Validation & Security│
└──────────┬───────────┘
           ▼
┌──────────────────────┐
│  Confirmation if req │
└──────────┬───────────┘
           ▼
┌──────────────────────┐
│    Tool Execution    │
└──────────┬───────────┘
           ▼
┌──────────────────────┐
│ Result Verification  │
└──────────┬───────────┘
           ▼
┌──────────────────────┐
│ Natural Language     │
│     Response         │
└──────────┬───────────┘
           ▼
┌──────────────────────┐
│        User          │
└──────────────────────┘
```

---

## OpenRouter Integration

Beta 1 uses OpenRouter as the inference provider so COLUM isn't locked to a single model.

**Modes**

| Mode       | Behavior                                         |
|------------|--------------------------------------------------|
| `free`     | Auto-pick a free model based on strategy         |
| `paid`     | Use configured paid models                       |
| `specific` | Use one exact model via `OPENROUTER_MODEL=provider/model-name` |

**Supported capabilities**
- Dynamic selection
- Automatic fallback
- Model capability detection
- Reasoning models
- Tool-capable models
- Streaming responses
- Provider abstraction

---

## Voice System

```
Mic → STT → COLUM Brain → TTS → Speaker
```

**STT providers**: Whisper Local, Whisper API, Google, Azure, Vosk
**TTS providers**: Edge, Google, Azure, Coqui, Piper
**Wake word**: `COLUM`

---

## Web & Desktop Automation

### Web
- Search
- Browse
- Extract info
- Research
- Collect structured data

### Desktop
- **Apps**: open, close, detect, focus
- **Windows**: move, resize, minimize, maximize, focus, close
- **Files**: create, read, write, move, rename, copy, delete, search, organize
- **Input**: keyboard, mouse
- **Screenshots**

All actions pass through the tool and security layers.

---

## Memory System

Memory is separated from the AI provider so the model can change without rebuilding memory.

- Conversation memory
- Task history
- User preferences
- Session context
- Automation state
- Long-term context

---

## Frontend & Dashboard

Built with vanilla **HTML / CSS / JavaScript**, communicating over HTTP and WebSocket.

**UI principles**: minimal, monochrome, technical, fast, responsive, low visual noise.

**Live status example**
```
COLUM STATUS
─────────────
AI              ONLINE
VOICE           READY
TOOLS           READY
MEMORY          READY
AUTOMATION      IDLE
SECURITY        ACTIVE
```

---

## Project Structure

```
COLUM/
├── app/
│   ├── ai/
│   ├── automation/
│   ├── config/
│   ├── core/
│   ├── memory/
│   ├── security/
│   ├── tools/
│   ├── utils/
│   ├── voice/
│   └── main.py
├── frontend/
│   ├── assets/
│   ├── css/
│   ├── js/
│   └── index.html
├── Project Plan/COLUM_Beta_1_Plan/
├── assets/
├── tests/
├── scripts/
├── .env.example
├── config.yaml
├── requirements.txt
└── README.md
```

---

## Installation

**Requirements**
- Windows 10 or 11
- Python 3.10+
- Git
- OpenRouter API key

**Clone**
```bash
git clone https://github.com/Alshahriar-07/COLUM.git
cd COLUM
```

**Automated setup**
```powershell
.\scripts\setup.ps1
```

**Manual setup**
```bash
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
copy .env.example .env
notepad .env
```

Add your OpenRouter API key to `.env`.

---

## Running COLUM

**Using the script**
```powershell
.\scripts\run.ps1
```

**Manual**
```powershell
.\.venv\Scripts\Activate.ps1
python -m app.main
```

**Default endpoints**

| Service   | Address                 |
|-----------|-------------------------|
| Dashboard | `http://localhost:8765` |
| WebSocket | `ws://localhost:8766`   |

---

## Configuration

Settings come from environment variables (`.env`) and `config.yaml`.

```env
# Required
OPENROUTER_API_KEY=your_key_here

# AI
OPENROUTER_MODE=free
OPENROUTER_MODEL=

# Wake Word
COLUM_WAKE_WORD=COLUM

# Runtime
COLUM_INACTIVITY_TIMEOUT_MINUTES=5

# Voice
VOICE_STT_PROVIDER=whisper_local
VOICE_TTS_PROVIDER=edge

# Logging
LOG_LEVEL=INFO
```

**Security rules**
- `.env` is private, never committed
- `.env.example` holds safe placeholders only
- API keys stay outside source code

---

## Example Commands

| Category      | Example                                                              |
|---------------|----------------------------------------------------------------------|
| Application   | "Open Chrome"                                                        |
| Search        | "Search for Python tutorials on YouTube"                             |
| Files         | "Create a file called notes.txt with Hello World"                    |
| Screenshot    | "Take a screenshot"                                                  |
| Information   | "What's the weather in Tokyo?"                                       |
| Organization  | "Create a folder called Projects in Downloads"                       |
| Multi-step    | "Open Chrome, search for the latest Python news, and summarize it."  |

---

## HTTP & WebSocket

**HTTP** (`http://localhost:8765`)
- Dashboard
- REST-style operations
- Health checks
- Config and state endpoints

**WebSocket** (`ws://localhost:8766`)
- Real-time events
- Streaming responses
- Tool and runtime status
- Voice state
- Dashboard sync

---

## Logging & Testing

**Logging**
- Runtime diagnostics, tool tracking, AI lifecycle, errors, warnings, debugging, security auditing
- Default level: `INFO`
- API keys are never logged

**Testing**
```bash
pytest tests/ -v
```

Future coverage: core, config, AI, tools, security, automation, memory, voice, frontend communication, end-to-end workflows.

---

## Code Quality

```bash
ruff check app/
ruff format app/
mypy app/
```

**Workflow**
```
Code → Format → Lint → Type Check → Test → Commit
```

---

## Roadmap

| Phase | Focus                                                 |
|-------|-------------------------------------------------------|
| 1     | Foundation ✓ structure, config, logging, HTTP, WS, dashboard, docs, security and tool architecture |
| 2     | AI Brain — OpenRouter client, model manager, fallback, streaming, tool calling, planning |
| 3     | Desktop Tools — launcher, windows, files, screenshots, keyboard, mouse, system info |
| 4     | Web Automation — search, browser, extraction, research |
| 5     | Voice — STT, TTS, wake word, VAD, pipelines           |
| 6     | Memory — conversation, history, preferences, retrieval |
| 7     | Advanced Automation — queues, retries, scheduling, monitoring |

---

## Beta 1 Documentation

Full planning lives in `Project Plan/COLUM_Beta_1_Plan/`:

| Document                  | Purpose                       |
|---------------------------|-------------------------------|
| `COLUM_BETA_1_SPEC.md`    | Complete Beta 1 specification |
| `ARCHITECTURE.md`         | System architecture           |
| `COMPONENTS.md`           | Component responsibilities    |
| `MODEL_STRATEGY.md`       | AI/model strategy             |
| `SECURITY.md`             | Security architecture         |
| `TOOL_MATRIX.md`          | Tool capability matrix        |
| `VOICE_LIFECYCLE.md`      | Voice lifecycle               |
| `WORKSPACES.md`           | Workspace architecture        |
| `TEST_PLAN.md`            | Testing strategy              |
| `ROADMAP.md`              | Development roadmap           |
| `INSTALL_AND_RUN.md`      | Installation guide            |
| `IMPLEMENTATION_NOTES.md` | Implementation guidance       |
| `COMMAND_EXAMPLES.md`     | Example commands              |
| `PROJECT_STRUCTURE.md`    | Project structure             |
| `MANIFEST.json`           | Project manifest              |

---

## Branding & Assets

**Identity**: monochrome, no gradients, no decorative noise.

| Mode  | Background | Elements | Text   | Borders   |
|-------|------------|----------|--------|-----------|
| Light | White      | Black    | Black  | Gray      |
| Dark  | Near Black | White    | White  | Dark Gray |

Assets live in `assets/`: banners, icons, favicon, wordmark, ICO/SVG variants. Frontend copies are in `frontend/assets/`.

---

## Current Status

```
┌───────────────────────────────────────┐
│          COLUM BETA 1 STATUS          │
├───────────────────────────────────────┤
│ Project Structure       ✓             │
│ Configuration           ✓             │
│ Logging                 ✓             │
│ Core Runtime            ✓             │
│ HTTP Server             ✓             │
│ WebSocket Foundation    ✓             │
│ Frontend Foundation     ✓             │
│ AI Integration          →             │
│ Tool System             →             │
│ Security Runtime        →             │
│ Automation              →             │
│ Memory                  →             │
│ Voice                   →             │
└───────────────────────────────────────┘
```

Beta 1 is the foundation layer. The goal is to get the architecture right before adding power.

---

## Security Notice

COLUM controls your desktop. As tools grow, the impact of a bad action grows too.

> **Never connect an LLM directly to unrestricted system execution.**

Always use:
```
AI → Tool Schema → Validation → Permission → Risk Check → Confirmation → Execution
<div align="center">

<img src="assets/banner.png" alt="COLUM Banner" width="100%">

# COLUM

### Computer Operating & Logic Utility Machine

**An AI desktop assistant and intelligent control layer for Windows.**

<br>

<img src="assets/icon-128.png" alt="COLUM Icon" width="96">

<br><br>

[![Beta](https://img.shields.io/badge/COLUM-Beta%201-000?style=for-the-badge)](https://github.com/Alshahriar-07/COLUM)
[![Windows](https://img.shields.io/badge/Windows-10%20%2F%2011-000?style=for-the-badge&logo=windows&logoColor=white)](https://www.microsoft.com/windows)
[![Python](https://img.shields.io/badge/Python-3.10%2B-000?style=for-the-badge&logo=python&logoColor=white)](https://www.python.org/)
[![Frontend](https://img.shields.io/badge/Frontend-HTML%20%2F%20CSS%20%2F%20JS-000?style=for-the-badge)](https://developer.mozilla.org/)
[![License](https://img.shields.io/badge/License-MIT-000?style=for-the-badge)](#license)

<br>

> **Understand. Plan. Control.**

COLUM is an AI-powered desktop assistant that understands natural language, reasons about tasks, safely executes approved actions, talks through voice or text, and acts as an intelligent control layer for Windows.

</div>

---

## Table of Contents

- [What is COLUM?](#what-is-colum)
- [Why COLUM?](#why-colum)
- [Design Philosophy](#design-philosophy)
- [Beta 1 Goals](#beta-1-goals)
- [Architecture](#architecture)
- [Core Components](#core-components)
- [Security Model](#security-model)
- [Command Lifecycle](#command-lifecycle)
- [OpenRouter Integration](#openrouter-integration)
- [Voice System](#voice-system)
- [Web & Desktop Automation](#web--desktop-automation)
- [Memory System](#memory-system)
- [Frontend & Dashboard](#frontend--dashboard)
- [Project Structure](#project-structure)
- [Installation](#installation)
- [Running COLUM](#running-colum)
- [Configuration](#configuration)
- [Example Commands](#example-commands)
- [HTTP & WebSocket](#http--websocket)
- [Logging & Testing](#logging--testing)
- [Code Quality](#code-quality)
- [Roadmap](#roadmap)
- [Beta 1 Documentation](#beta-1-documentation)
- [Branding & Assets](#branding--assets)
- [Current Status](#current-status)
- [Security Notice](#security-notice)
- [Future Vision](#future-vision)
- [Contributing](#contributing)
- [License](#license)
- [Support](#support)

---

## What is COLUM?

**COLUM** = **Computer Operating & Logic Utility Machine**

Inspired by JARVIS, COLUM is not just a chatbot. It's a complete **AI operating and control layer** for your computer that can:

- Understand natural language
- Reason about your intent
- Break complex requests into tasks
- Choose the right tools for the job
- Ask for confirmation when needed
- Execute desktop operations safely
- Control applications, files, and windows
- Perform web tasks
- Respond by voice or text
- Remember context across sessions

The LLM never touches your operating system directly. Every action goes through a structured pipeline.

---

## Why COLUM?

Most AI assistants live inside a chat box. COLUM bridges:

```
AI  +  Desktop  +  Automation  +  Voice  +  Memory  +  Security
```

into one modular system.

**Example request:**
> *"Open Chrome and search YouTube for Python tutorials."*

**COLUM does this:**
1. Understand the request
2. Build an execution plan
3. Pick the right tools
4. Validate parameters
5. Execute approved actions
6. Verify the result
7. Reply in natural language

**More complex request:**
> *"Organize today's screenshots into a folder."*

1. Detect today's date
2. Find screenshot files
3. Create the destination folder
4. Ask for confirmation if needed
5. Move approved files
6. Verify and report

---

## Design Philosophy

Every request flows through one pipeline:

```
Understand
    ↓
Reason
    ↓
Plan
    ↓
Validate
    ↓
Confirm
    ↓
Execute
    ↓
Verify
    ↓
Report
```

- **LLM** → reasons and plans
- **Local runtime** → enforces security and executes

This separation is the most important principle of the project.

---

## Beta 1 Goals

Beta 1 builds the production-ready foundation:

- Core application architecture
- Python backend
- Configuration management
- Logging
- HTTP server
- WebSocket communication
- HTML / CSS / JS dashboard
- OpenRouter integration
- AI model management
- Tool, security, memory, voice, automation architectures
- Testing foundation
- Full project documentation

Beta 1 deliberately avoids training a custom model. OpenRouter is the initial inference layer.

---

## Architecture

```
                           ┌─────────────────────────┐
                           │       USER / VOICE      │
                           └────────────┬────────────┘
                                        │
                                        ▼
                           ┌─────────────────────────┐
                           │      COLUM FRONTEND     │
                           │       HTML/CSS/JS       │
                           └────────────┬────────────┘
                                        │
                              HTTP / WebSocket
                                        │
                                        ▼
                           ┌─────────────────────────┐
                           │       COLUM CORE        │
                           │ Lifecycle + Event Bus   │
                           └────────────┬────────────┘
                                        │
        ┌───────────────────────────────┼───────────────────────────────┐
        │                               │                               │
        ▼                               ▼                               ▼
┌───────────────┐              ┌───────────────┐              ┌───────────────┐
│   AI LAYER    │              │  AUTOMATION   │              │    MEMORY     │
│  OpenRouter   │              │   Execution   │              │ Context/State │
│ Model Manager │              │   Planning    │              │ Preferences   │
└───────┬───────┘              └───────┬───────┘              └───────────────┘
        │                              │
        └──────────────┬───────────────┘
                       │
                       ▼
              ┌─────────────────┐
              │   TOOL SYSTEM   │
              │  Validation     │
              │  Permissions    │
              │  Execution      │
              └────────┬────────┘
                       │
        ┌──────────────┼──────────────┐
        │              │              │
        ▼              ▼              ▼
┌──────────────┐ ┌──────────────┐ ┌──────────────┐
│   DESKTOP    │ │     WEB      │ │    VOICE     │
│   CONTROL    │ │ AUTOMATION   │ │   STT / TTS  │
└──────────────┘ └──────────────┘ └──────────────┘
```

---

## Core Components

### AI Layer
Handles OpenRouter communication, model selection, fallback, prompt construction, reasoning, planning, tool selection, structured tool calls, and streaming. It never executes OS actions directly.

### Core Runtime
The central infrastructure: lifecycle, startup/shutdown, events, internal communication, HTTP and WebSocket servers, runtime state, error handling, logging integration.

### Tool System
The bridge between AI reasoning and the real system.

```
AI Decision
     ↓
Tool Request
     ↓
Schema Validation
     ↓
Permission Check
     ↓
Risk Assessment
     ↓
Execution
     ↓
Result
```

Planned tools: application launcher, file manager, window manager, keyboard, mouse, screenshot, system info, browser automation, web search, controlled terminal.

---

## Security Model

The AI never gets unrestricted OS access. Every action passes through a risk pipeline:

```
AI Tool Request
        ↓
Parameter Validation
        ↓
Permission Check
        ↓
Risk Classifier
        ↓
   LOW  |  MEDIUM  |  HIGH
   ↓         ↓         ↓
Execute   Policy    Confirmation
                    ↓
              User Approval
                    ↓
                  Execute
```

**Principles**
- No unrestricted LLM shell access
- Structured tool execution
- Parameter validation
- Permission-aware actions
- High-risk confirmation
- API keys never logged
- Sensitive data kept out of prompts when possible
- All actions are auditable

---

## Command Lifecycle

```
┌──────────────────────┐
│      User Input      │
└──────────┬───────────┘
           ▼
┌──────────────────────┐
│  Input Normalization │
└──────────┬───────────┘
           ▼
┌──────────────────────┐
│    Intent Analysis   │
└──────────┬───────────┘
           ▼
┌──────────────────────┐
│  AI Reasoning/Plan   │
└──────────┬───────────┘
           ▼
┌──────────────────────┐
│    Tool Selection    │
└──────────┬───────────┘
           ▼
┌──────────────────────┐
│ Validation & Security│
└──────────┬───────────┘
           ▼
┌──────────────────────┐
│  Confirmation if req │
└──────────┬───────────┘
           ▼
┌──────────────────────┐
│    Tool Execution    │
└──────────┬───────────┘
           ▼
┌──────────────────────┐
│ Result Verification  │
└──────────┬───────────┘
           ▼
┌──────────────────────┐
│ Natural Language     │
│     Response         │
└──────────┬───────────┘
           ▼
┌──────────────────────┐
│        User          │
└──────────────────────┘
```

---

## OpenRouter Integration

Beta 1 uses OpenRouter as the inference provider so COLUM isn't locked to a single model.

**Modes**

| Mode       | Behavior                                         |
|------------|--------------------------------------------------|
| `free`     | Auto-pick a free model based on strategy         |
| `paid`     | Use configured paid models                       |
| `specific` | Use one exact model via `OPENROUTER_MODEL=provider/model-name` |

**Supported capabilities**
- Dynamic selection
- Automatic fallback
- Model capability detection
- Reasoning models
- Tool-capable models
- Streaming responses
- Provider abstraction

---

## Voice System

```
Mic → STT → COLUM Brain → TTS → Speaker
```

**STT providers**: Whisper Local, Whisper API, Google, Azure, Vosk
**TTS providers**: Edge, Google, Azure, Coqui, Piper
**Wake word**: `COLUM`

---

## Web & Desktop Automation

### Web
- Search
- Browse
- Extract info
- Research
- Collect structured data

### Desktop
- **Apps**: open, close, detect, focus
- **Windows**: move, resize, minimize, maximize, focus, close
- **Files**: create, read, write, move, rename, copy, delete, search, organize
- **Input**: keyboard, mouse
- **Screenshots**

All actions pass through the tool and security layers.

---

## Memory System

Memory is separated from the AI provider so the model can change without rebuilding memory.

- Conversation memory
- Task history
- User preferences
- Session context
- Automation state
- Long-term context

---

## Frontend & Dashboard

Built with vanilla **HTML / CSS / JavaScript**, communicating over HTTP and WebSocket.

**UI principles**: minimal, monochrome, technical, fast, responsive, low visual noise.

**Live status example**
```
COLUM STATUS
─────────────
AI              ONLINE
VOICE           READY
TOOLS           READY
MEMORY          READY
AUTOMATION      IDLE
SECURITY        ACTIVE
```

---

## Project Structure

```
COLUM/
├── app/
│   ├── ai/
│   ├── automation/
│   ├── config/
│   ├── core/
│   ├── memory/
│   ├── security/
│   ├── tools/
│   ├── utils/
│   ├── voice/
│   └── main.py
├── frontend/
│   ├── assets/
│   ├── css/
│   ├── js/
│   └── index.html
├── Project Plan/COLUM_Beta_1_Plan/
├── assets/
├── tests/
├── scripts/
├── .env.example
├── config.yaml
├── requirements.txt
└── README.md
```

---

## Installation

**Requirements**
- Windows 10 or 11
- Python 3.10+
- Git
- OpenRouter API key

**Clone**
```bash
git clone https://github.com/Alshahriar-07/COLUM.git
cd COLUM
```

**Automated setup**
```powershell
.\scripts\setup.ps1
```

**Manual setup**
```bash
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
copy .env.example .env
notepad .env
```

Add your OpenRouter API key to `.env`.

---

## Running COLUM

**Using the script**
```powershell
.\scripts\run.ps1
```

**Manual**
```powershell
.\.venv\Scripts\Activate.ps1
python -m app.main
```

**Default endpoints**

| Service   | Address                 |
|-----------|-------------------------|
| Dashboard | `http://localhost:8765` |
| WebSocket | `ws://localhost:8766`   |

---

## Configuration

Settings come from environment variables (`.env`) and `config.yaml`.

```env
# Required
OPENROUTER_API_KEY=your_key_here

# AI
OPENROUTER_MODE=free
OPENROUTER_MODEL=

# Wake Word
COLUM_WAKE_WORD=COLUM

# Runtime
COLUM_INACTIVITY_TIMEOUT_MINUTES=5

# Voice
VOICE_STT_PROVIDER=whisper_local
VOICE_TTS_PROVIDER=edge

# Logging
LOG_LEVEL=INFO
```

**Security rules**
- `.env` is private, never committed
- `.env.example` holds safe placeholders only
- API keys stay outside source code

---

## Example Commands

| Category      | Example                                                              |
|---------------|----------------------------------------------------------------------|
| Application   | "Open Chrome"                                                        |
| Search        | "Search for Python tutorials on YouTube"                             |
| Files         | "Create a file called notes.txt with Hello World"                    |
| Screenshot    | "Take a screenshot"                                                  |
| Information   | "What's the weather in Tokyo?"                                       |
| Organization  | "Create a folder called Projects in Downloads"                       |
| Multi-step    | "Open Chrome, search for the latest Python news, and summarize it."  |

---

## HTTP & WebSocket

**HTTP** (`http://localhost:8765`)
- Dashboard
- REST-style operations
- Health checks
- Config and state endpoints

**WebSocket** (`ws://localhost:8766`)
- Real-time events
- Streaming responses
- Tool and runtime status
- Voice state
- Dashboard sync

---

## Logging & Testing

**Logging**
- Runtime diagnostics, tool tracking, AI lifecycle, errors, warnings, debugging, security auditing
- Default level: `INFO`
- API keys are never logged

**Testing**
```bash
pytest tests/ -v
```

Future coverage: core, config, AI, tools, security, automation, memory, voice, frontend communication, end-to-end workflows.

---

## Code Quality

```bash
ruff check app/
ruff format app/
mypy app/
```

**Workflow**
```
Code → Format → Lint → Type Check → Test → Commit
```

---

## Roadmap

| Phase | Focus                                                 |
|-------|-------------------------------------------------------|
| 1     | Foundation ✓ structure, config, logging, HTTP, WS, dashboard, docs, security and tool architecture |
| 2     | AI Brain — OpenRouter client, model manager, fallback, streaming, tool calling, planning |
| 3     | Desktop Tools — launcher, windows, files, screenshots, keyboard, mouse, system info |
| 4     | Web Automation — search, browser, extraction, research |
| 5     | Voice — STT, TTS, wake word, VAD, pipelines           |
| 6     | Memory — conversation, history, preferences, retrieval |
| 7     | Advanced Automation — queues, retries, scheduling, monitoring |

---

## Beta 1 Documentation

Full planning lives in `Project Plan/COLUM_Beta_1_Plan/`:

| Document                  | Purpose                       |
|---------------------------|-------------------------------|
| `COLUM_BETA_1_SPEC.md`    | Complete Beta 1 specification |
| `ARCHITECTURE.md`         | System architecture           |
| `COMPONENTS.md`           | Component responsibilities    |
| `MODEL_STRATEGY.md`       | AI/model strategy             |
| `SECURITY.md`             | Security architecture         |
| `TOOL_MATRIX.md`          | Tool capability matrix        |
| `VOICE_LIFECYCLE.md`      | Voice lifecycle               |
| `WORKSPACES.md`           | Workspace architecture        |
| `TEST_PLAN.md`            | Testing strategy              |
| `ROADMAP.md`              | Development roadmap           |
| `INSTALL_AND_RUN.md`      | Installation guide            |
| `IMPLEMENTATION_NOTES.md` | Implementation guidance       |
| `COMMAND_EXAMPLES.md`     | Example commands              |
| `PROJECT_STRUCTURE.md`    | Project structure             |
| `MANIFEST.json`           | Project manifest              |

---

## Branding & Assets

**Identity**: monochrome, no gradients, no decorative noise.

| Mode  | Background | Elements | Text   | Borders   |
|-------|------------|----------|--------|-----------|
| Light | White      | Black    | Black  | Gray      |
| Dark  | Near Black | White    | White  | Dark Gray |

Assets live in `assets/`: banners, icons, favicon, wordmark, ICO/SVG variants. Frontend copies are in `frontend/assets/`.

---

## Current Status

```
┌───────────────────────────────────────┐
│          COLUM BETA 1 STATUS          │
├───────────────────────────────────────┤
│ Project Structure       ✓             │
│ Configuration           ✓             │
│ Logging                 ✓             │
│ Core Runtime            ✓             │
│ HTTP Server             ✓             │
│ WebSocket Foundation    ✓             │
│ Frontend Foundation     ✓             │
│ AI Integration          →             │
│ Tool System             →             │
│ Security Runtime        →             │
│ Automation              →             │
│ Memory                  →             │
│ Voice                   →             │
└───────────────────────────────────────┘
```

Beta 1 is the foundation layer. The goal is to get the architecture right before adding power.

---

## Security Notice

COLUM controls your desktop. As tools grow, the impact of a bad action grows too.

> **Never connect an LLM directly to unrestricted system execution.**

Always use:
```
AI → Tool Schema → Validation → Permission → Risk Check → Confirmation → Execution
