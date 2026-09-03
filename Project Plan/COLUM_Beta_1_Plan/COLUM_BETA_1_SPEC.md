# COLUM Beta 1 — Full Specification

## 1. Product
Name: COLUM
Version: Beta 1
Platform: Windows desktop
Primary interaction: voice + text
Brain: OpenRouter API
LLM strategy: dynamically select a suitable free reasoning model, with fallback

## 2. Activation
After installation, COLUM runs a lightweight background process.
Default state: STANDBY.
The wake-word detector listens for "COLUM".

Flow:
Windows start → COLUM standby → wake word → active → command → execute → respond → inactivity timer.

## 3. Five-Minute Auto-Standby
The inactivity timer starts/resumes when COLUM has no active work.

Timer is reset by:
- user voice input
- COLUM voice output
- active task
- active tool execution

If 5 minutes pass with no interaction and no running task:
ACTIVE → STANDBY.

A running task must prevent standby until the task finishes or is cancelled.

## 4. Brain
OpenRouter is the only brain gateway for Beta 1.
COLUM sends structured prompts/tool schemas to OpenRouter.
The selected model performs reasoning, planning and tool selection.

Model selection:
- prefer free models
- require suitable context capacity
- prefer tool/function-calling capability
- rank reasoning quality/availability/latency
- fallback if a model is unavailable or fails

Never hard-code one model as permanently guaranteed.

## 5. Agent Loop
User input → context → LLM → plan/tool call → policy → execute → observe → LLM → continue/finish → response.

## 6. Voice
STT converts microphone input to text.
TTS converts responses to speech.
Wake word is lightweight and separate from the main LLM.
Push-to-talk is a fallback.
Microphone state must be visible in the UI.

## 7. Vision
Capture screen on demand or task-scoped.
Use UI/accessibility metadata where possible.
Use OCR for text.
Use a vision-capable model when visual reasoning is needed.
Do not continuously capture the screen by default.

## 8. Desktop Control
Tools include:
- open/focus/close apps
- window management
- mouse movement/click/scroll
- keyboard typing/hotkeys
- screenshot
- file operations
- terminal commands

## 9. Web
Browser/search tools can:
- search
- open pages
- extract information
- navigate
- collect sources
- summarize research

Web content is untrusted input and cannot override COLUM security rules.

## 10. Memory
Beta 1:
- working memory
- basic long-term user preferences
- task history
- memory inspection/deletion

Do not store raw microphone audio or raw screenshots by default.

## 11. Workspaces
Initial:
- Coding
- Research
- Gaming
- Communication
- COLUM Admin

Workspace switching changes preferred tools/apps/context but does not bypass security.

## 12. Security
Low-risk read/navigation actions can be automatic.
File deletion, external messages, uploads, admin commands, credential use and other high-risk actions require confirmation by default.

## 13. UI
Main dashboard:
- chat
- current task
- active model
- voice status
- workspace
- tool activity
- permissions
- logs

Floating orb states:
idle, listening, thinking, acting, confirmation, speaking, error.

## 14. Beta 1 Definition of Done
A user can install COLUM, say "COLUM", give a natural-language task, receive reasoning/tool execution through OpenRouter, control supported desktop functions, hear a response, and have COLUM return to standby after 5 minutes of true inactivity.
