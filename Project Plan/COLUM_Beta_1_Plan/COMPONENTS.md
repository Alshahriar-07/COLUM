# COLUM Beta 1 Components

## OpenRouter Gateway
Calls OpenRouter, normalizes responses and tool calls, handles errors and retries.

## Free Model Selector
Discovers/configures candidate free models and ranks them for reasoning, tool use, context, latency and availability.

## Orchestrator
Owns the agent loop and task lifecycle.

## Wake Word
Detects "COLUM" locally/lightweight and transitions standby → active.

## Activity Manager
Tracks voice input, TTS output and tool/task activity. Owns the 5-minute inactivity policy.

## STT
Speech-to-text.

## TTS
Text-to-speech.

## Vision
Screenshot + OCR + optional vision model.

## Desktop Tools
Mouse, keyboard, windows and apps.

## Files
Safe file search/read/write/move/copy/rename/delete.

## Terminal
Controlled shell execution with risk checks.

## Browser
Search/navigation/extraction and controlled page interaction.

## Memory
Working context and user-approved persistent preferences.

## Workspace
Switches task environments.

## Security
Risk classification, confirmation and audit.

## UI
Main window, floating orb and settings/dashboard.
