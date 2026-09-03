# COLUM Beta 1 Architecture

COLUM is a modular agent, not a custom LLM.

Windows
  ↓
COLUM Background Runtime
  ↓
Wake Word / Lifecycle Manager
  ↓
Agent Orchestrator
  ├── OpenRouter Model Gateway
  ├── Voice Service
  ├── Vision Service
  ├── Web Agent
  ├── Tool Registry/Executor
  ├── Memory
  ├── Workspace Manager
  └── Security/Policy

Agent loop:
Input → Context → Plan → Policy → Tool → Observation → Re-plan → Result

Important separation:
- LLM decides what should happen.
- Policy decides whether it is allowed.
- Tool executor performs the action.
- Observation reports what actually happened.
