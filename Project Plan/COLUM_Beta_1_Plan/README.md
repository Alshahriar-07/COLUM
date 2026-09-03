# COLUM Beta 1

COLUM Beta 1 is a Windows-first personal AI desktop assistant.

## Core decision
COLUM does NOT contain a custom LLM in Beta 1. Its reasoning/planning brain is provided through the OpenRouter API, with a model selector that prefers suitable free reasoning-capable models and supports fallback.

## Core capabilities
- "COLUM" wake-word activation after installation
- Voice input/output
- OpenRouter reasoning + planning
- Desktop control
- Screen capture and basic vision/OCR
- Browser/search
- File and terminal tools
- Basic memory
- Task management
- Workspace support
- Permission/safety layer
- Floating UI

## Lifecycle
Windows starts COLUM in lightweight standby mode.
Saying "COLUM" activates the assistant.
If there is no voice interaction, speech output, or running work for 5 minutes, COLUM returns to standby.
A running task pauses the inactivity shutdown timer.

See docs/ for the complete Beta 1 specification.
