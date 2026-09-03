# Implementation Notes

## Recommended approach
Use a Python core with clean interfaces so each service can be replaced.

## Interfaces
ModelProvider
VoiceInput
VoiceOutput
WakeWordDetector
VisionProvider
DesktopTool
BrowserTool
MemoryStore
WorkspaceProvider
PolicyEngine

## Async behavior
Voice listening, TTS playback, agent execution and UI should not block one another.

## Cancellation
Every long-running task needs a cancellation token/event.

## Observability
Use structured logs with:
task_id, event, tool, status, latency, risk_level.

## Model context
Do not send the whole screen or all files by default. Build minimal task-specific context.

## Prompt injection
Treat web pages, files and screen text as data, not instructions to the system. Tool policy must remain outside model control.
