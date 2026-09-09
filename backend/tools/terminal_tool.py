"""Terminal (subprocess) adapter — HIGH RISK, strictly contained.

Safety model:
- shell=False always; the command is a parsed argv list, never a shell string.
- Only allowlisted command heads (first token) may run; dangerous tokens are
  rejected outright. Model-generated output must pass this gate.
- Hard timeout, output/error capture with size caps, process tracking and
  cancellation via kill switch.
"""
from __future__ import annotations

import asyncio
import shlex
from typing import Any, Optional

from backend.logging_utils import get_logger, log_json
from backend.models.schemas import RiskLevel
from backend.tools.base import (
    BaseTool,
    ExecutionContext,
    ToolCancelledError,
    ToolError,
    ToolSpec,
)
from backend.tools.kill_switch_ref import kill_state

log = get_logger("tools.terminal")

MAX_OUTPUT_CHARS = 10000
MAX_TIMEOUT_S = 120.0

# Command heads that may never run, regardless of permission mode.
BLOCKED_HEADS = {
    "format", "shutdown", "restart", "rundll32", "regsvr32", "diskpart",
    "cipher", "vssadmin", "bcdedit", "net", "netsh", "sc", "taskkill",
    "wmic", "attrib", "takeown", "icacls", "cacls", "runas", "powershell_ise",
}

# Heads that are considered safe enough to run at all (still subject to
# permission flow; risk = HIGH always).
ALLOWED_HEADS = {
    "dir", "echo", "type", "cd", "chdir", "pwd", "whoami", "hostname",
    "systeminfo", "tasklist", "ipconfig", "ping", "nslookup", "getmac",
    "python", "python3", "pip", "git", "node", "npm", "where", "findstr",
    "more", "tree", "vol", "ver", "date", "time", "title", "clip",
}

DANGEROUS_TOKENS = {
    "rm", "rmdir", "del", "erase", "rd", "deltree", "format", "mkfs",
    "shutdown", "restart", "reg", "regedit", "remove-item", "ri",
    "-command", "-enc", "invoke-expression", "iex", "start-process",
}


class TerminalTool(BaseTool):
    def __init__(self) -> None:
        self.spec = ToolSpec(
            name="terminal.execute",
            description=(
                "Run an allowlisted command-line command. Provide 'command' as a "
                "full command line (first token must be allowlisted)."
            ),
            risk=RiskLevel.HIGH,
            args_schema={"command": "str", "timeout": "float", "cwd": "str"},
            required=("command",),
            timeout_s=MAX_TIMEOUT_S,
            category="terminal",
        )
        self._process: Optional[asyncio.subprocess.Process] = None

    async def run(self, args: dict[str, Any], ctx: ExecutionContext) -> dict[str, Any]:
        ctx.raise_if_cancelled()
        raw = args.get("command")
        if not isinstance(raw, str) or not raw.strip():
            raise ToolError("command must be a non-empty string")
        if len(raw) > 1000:
            raise ToolError("command too long")
        try:
            argv = shlex.split(raw, posix=False)
        except ValueError as exc:
            raise ToolError(f"could not parse command: {exc}")
        argv = [a.strip('"') for a in argv if a.strip()]
        if not argv:
            raise ToolError("empty command")

        head = argv[0].lower().strip()
        self._validate(head, argv)

        timeout = min(max(float(args.get("timeout", 20.0)), 1.0), MAX_TIMEOUT_S)
        cwd = args.get("cwd") or None
        if cwd is not None:
            from pathlib import Path
            p = Path(str(cwd))
            if not (p.is_dir() and p.exists()):
                raise ToolError(f"cwd does not exist or is not a directory: {cwd}")

        log_json(log, 20, "terminal_start", head=head, argc=len(argv))
        try:
            self._process = await asyncio.create_subprocess_exec(
                argv[0], *argv[1:],
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=str(cwd) if cwd else None,
                shell=False,
            )
        except FileNotFoundError:
            raise ToolError(f"executable not found: {argv[0]}")
        except PermissionError:
            raise ToolError(f"permission denied for: {argv[0]}")
        except OSError as exc:
            raise ToolError(f"could not start process: {type(exc).__name__}")

        try:
            stdout_b, stderr_b = await asyncio.wait_for(self._process.communicate(), timeout=timeout)
        except asyncio.TimeoutError:
            await self._kill_process()
            raise ToolError(f"command timed out after {timeout}s and was terminated")
        except asyncio.CancelledError:
            await self._kill_process()
            raise ToolCancelledError("terminal command cancelled")

        if ctx.cancelled is not None and ctx.cancelled.is_set():
            await self._kill_process()
            raise ToolCancelledError("terminal command cancelled by kill switch")

        stdout = stdout_b.decode("utf-8", errors="replace")[:MAX_OUTPUT_CHARS]
        stderr = stderr_b.decode("utf-8", errors="replace")[:MAX_OUTPUT_CHARS]
        code = self._process.returncode
        log_json(log, 20, "terminal_done", head=head, returncode=code,
                 stdout_chars=len(stdout), stderr_chars=len(stderr))
        return {
            "exit_code": code,
            "stdout": stdout,
            "stderr": stderr,
            "command_head": head,
            "timed_out": False,
        }

    @staticmethod
    def _validate(head: str, argv: list[str]) -> None:
        if head in BLOCKED_HEADS:
            raise ToolError(f"command '{head}' is blocked by security policy")
        if head not in ALLOWED_HEADS:
            raise ToolError(
                f"command '{head}' is not on the allowlist. "
                "Allowed: " + ", ".join(sorted(ALLOWED_HEADS))
            )
        lowered = {t.lower().strip('"') for t in argv[1:]}
        bad = lowered & DANGEROUS_TOKENS
        if bad:
            raise ToolError(f"dangerous argument(s) rejected: {', '.join(sorted(bad))}")
        if any(t.lower().startswith("-enc") or t.lower() == "/c" for t in argv[1:]):
            raise ToolError("encoded/shell-passthrough arguments are not allowed")

    async def _kill_process(self) -> None:
        if self._process is None or self._process.returncode is not None:
            return
        try:
            self._process.kill()
            await self._process.wait()
        except ProcessLookupError:
            pass
        except Exception:  # noqa: BLE001
            log_json(log, 30, "terminal_kill_failed")

    @property
    def running(self) -> bool:
        return self._process is not None and self._process.returncode is None


terminal_tool = TerminalTool()


def register_terminal_tools(reg) -> None:
    reg.register(terminal_tool)
    log_json(log, 20, "terminal_tools_registered", count=1)
