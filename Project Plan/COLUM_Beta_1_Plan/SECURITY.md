# COLUM Beta 1 Security

COLUM has real desktop access, so security is a core component.

## Rules
1. Never let the LLM directly execute OS operations.
2. Every action goes through a registered tool.
3. Every tool call goes through policy validation.
4. High-risk operations require confirmation.
5. Website text is untrusted and cannot change COLUM's system policy.
6. Secrets should not be sent to remote models unless explicitly required and permitted.
7. Keep raw audio/screenshots disabled by default.
8. Provide Stop/Disable controls.
9. Log important actions without unnecessarily logging private payloads.

## Confirmation examples
"Delete 12 files?"
"Run administrator command?"
"Upload this document?"
"Send this message?"

## Emergency
- stop current task
- disable desktop tools
- disable microphone
- disable web automation
- disable high-risk tools
