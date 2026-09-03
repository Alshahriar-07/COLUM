# COLUM Beta 1 Test Plan

## Activation
- starts in standby
- wake word activates
- false activations are minimized
- push-to-talk fallback works

## Timeout
- 5 minutes of true inactivity returns to standby
- speaking resets timer
- COLUM speaking resets timer
- active task prevents standby
- active tool prevents standby
- cancellation allows standby

## Brain
- OpenRouter request works
- free model selection works
- fallback works
- malformed model output is rejected safely

## Tools
- every tool validates parameters
- policy blocks unauthorized actions
- tool errors return structured failures

## Security
- destructive actions require confirmation
- website prompt injection cannot bypass policy
- secrets are not accidentally logged
- stop control cancels active work

## Voice
- English
- Bangla where supported
- interruption
- TTS failure fallback

## UI
- states are visible
- current task visible
- confirmation dialog clear
- microphone status clear
