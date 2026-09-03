# COLUM Voice & Lifecycle

## States
STANDBY
LISTENING
THINKING
ACTING
SPEAKING
WAITING_CONFIRMATION
ERROR

## Startup
Windows → background runtime → initialize wake-word listener → STANDBY.

## Activation
Wake word "COLUM" → LISTENING → capture command → STT → orchestrator.

## Auto-standby
Track last meaningful activity.

Meaningful activity:
- user voice detected
- COLUM speaking
- task/tool execution
- confirmation interaction

If:
now - last_activity >= 5 minutes
AND no task/tool is active
AND COLUM is not speaking
then transition to STANDBY.

## Cancellation
User can say "COLUM, stop" or use a visible stop control.

## Failure
If STT/TTS/network/model fails, show a clear state and allow retry or text fallback.
