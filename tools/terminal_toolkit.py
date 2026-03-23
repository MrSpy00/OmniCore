"""Terminal Toolkit — host shell command execution.

Every command goes through the HITL Guardian (``is_destructive = True``)
because arbitrary shell execution is inherently dangerous.
"""

from __future__ import annotations

import asyncio
import os
import re
from pathlib import Path

from config.logging import get_logger
from models.tools import ToolInput, ToolOutput
from tools.base import BaseTool, resolve_user_path
from tools.os_adapters import ShellAdapterFactory

logger = get_logger(__name__)

# Hard limit to prevent runaway processes.
_DEFAULT_TIMEOUT_SECONDS = 60
_MAX_TIMEOUT_SECONDS = 300

_DENY_PATTERNS = (
    r"\brm\s+-rf\s+/",
    r"\bformat\s+c:\b",
    r"\bdiskpart\b.*\bclean\b",
    r"\breg\s+delete\s+hklm\\system\b",
    r"\bbcdedit\s+/delete\b",
)

_HIGH_RISK_MARKERS = (
    "remove-item",
    "del ",
    "delete",
    "shutdown",
    "restart-computer",
    "taskkill",
    "kill ",
    "format",
    "diskpart",
)

_ADMIN_MARKERS = (
    "hklm",
    "sc.exe",
    "netsh",
    "bcdedit",
    "diskpart",
)

_DEFENSIVE_BLOCK_MARKERS = (
    "createremotethread",
    "writeprocessmemory",
    "frida",
    "bpftrace",
    "rootkit",
    "seimpersonate",
    "memfd_create",
    "ptrace",
    "virtualallocex",
    "execveat",
    "commandlineeventconsumer create",
    "\\root\\subscription",
    "currentversion\\run",
    "insmod",
    "sysrq-trigger",
    "printspoofer",
    "roguewinrm",
    "fodhelper",
    "amsi bypass",
    "etweventwrite",
    "trustedinstaller",
    "dns tunneling",
    "ip spoofing",
    "mimikatz",
    "psexec -s",
    "\\\\.\\physicaldrive0",
    "vssadmin create shadow",
    "ntds.dit",
    "sam\\sam",
    "dd if=/dev/zero of=\\\\.\\physicaldrive0",
)

_PRIVILEGE_ESCALATION_MARKERS = (
    "seimpersonate",
    "trustedinstaller",
    "psexec -s",
    "fodhelper",
    "uac bypass",
)

_PERSISTENCE_MARKERS = (
    "commandlineeventconsumer create",
    "\\root\\subscription",
    "currentversion\\run",
    "sc create",
    "autorun",
    "bootkit",
    "uefi",
)

_STEALTH_MEMORY_MARKERS = (
    "memfd_create",
    "execveat",
    "virtualallocex",
    "createremotethread",
    "writeprocessmemory",
    "reflection.assembly.load",
    "add-type -typedefinition",
    "ptrace",
    "rwx",
)

_KERNEL_MANIPULATION_MARKERS = (
    "ring 0",
    "kernel space",
    "bpftrace",
    "ebpf",
    "insmod",
    "rmmod",
    "sysrq-trigger",
)

_RAW_DISK_ACCESS_MARKERS = (
    "\\\\.\\physicaldrive0",
    "mft parsing",
    "raw mft",
    "createfile(",
    "ntfsinfo",
    "vssadmin create shadow",
    "ntds.dit",
)

_NETWORK_SPOOFING_MARKERS = (
    "sock_raw",
    "ip spoofing",
    "custom packet injection",
    "ip netns add",
    "ip netns exec",
    "nftables",
    "iptables",
)

_REVERSE_ENGINEERING_MARKERS = (
    "windbg",
    "cdb.exe",
    "breakpoints",
    "int 3",
    "strace -f",
    "ltrace",
    "reverse engineering",
)

_SAFE_GUIDANCE = {
    "privilege_escalation": (
        "Privilege-escalation pattern blocked. "
        "Use least-privilege audit, token hardening, and approved access workflows."
    ),
    "persistence_abuse": (
        "Persistence pattern blocked. "
        "Use startup/service/WMI auditing and containment-cleanup procedures."
    ),
    "stealth_memory_abuse": (
        "Stealth memory-execution pattern blocked. "
        "Use EDR telemetry, memory inspection, and incident triage playbooks."
    ),
    "kernel_manipulation": (
        "Kernel-manipulation pattern blocked. "
        "Use kernel module audit, integrity checks, and approved hardening steps."
    ),
    "raw_disk_access": (
        "Raw disk-access pattern blocked. "
        "Use forensic-safe acquisition planning with explicit authorization and chain-of-custody."
    ),
    "network_spoofing": (
        "Network spoofing/injection pattern blocked. "
        "Use firewall diagnostics, packet capture, and authorized validation workflows."
    ),
    "reverse_engineering_abuse": (
        "Reverse-engineering abuse pattern blocked. "
        "Use approved debugging and observability approaches instead."
    ),
    "defensive_only": (
        "Command blocked by defensive-only policy. "
        "I can help with detection, hardening, and secure remediation steps instead."
    ),
}

_READONLY_COMMAND_PREFIXES = (
    "dir",
    "ls",
    "cat",
    "type",
    "echo",
    "findstr",
    "select-string",
    "grep",
    "find",
    "where",
    "get-",
    "systeminfo",
    "hostname",
    "whoami",
    "ipconfig",
    "ping",
    "tracert",
    "pathping",
    "netstat",
    "nslookup",
)


def _build_shell_command(command: str) -> tuple[list[str], str]:
    return ShellAdapterFactory.get_adapter().build_command(command)


def _build_shell_command_preferred(command: str, preferred_shell: str) -> tuple[list[str], str]:
    return ShellAdapterFactory.get_adapter().build_command(command, preferred_shell)


def _analyze_command(command: str) -> dict[str, object]:
    normalized = (command or "").strip().lower()
    deny_match = any(re.search(pattern, normalized) for pattern in _DENY_PATTERNS)
    is_high_risk = any(marker in normalized for marker in _HIGH_RISK_MARKERS)
    needs_admin = any(marker in normalized for marker in _ADMIN_MARKERS)
    matched_marker = _first_matched_marker(normalized, _DEFENSIVE_BLOCK_MARKERS)
    blocked_defensive_only = bool(matched_marker)
    is_readonly = _is_read_only_command(normalized)

    risk_level = "low"
    if deny_match:
        risk_level = "critical"
    elif is_high_risk:
        risk_level = "high"
    return {
        "blocked": deny_match,
        "blocked_defensive_only": blocked_defensive_only,
        "risk_level": risk_level,
        "needs_admin": needs_admin,
        "read_only": is_readonly,
        "matched_defensive_marker": matched_marker,
        "blocked_category": _detect_marker_category(matched_marker),
    }


def _first_matched_marker(normalized_command: str, markers: tuple[str, ...]) -> str:
    for marker in markers:
        if marker in normalized_command:
            return marker
    return ""


def _detect_marker_category(marker: str) -> str:
    if not marker:
        return ""
    if marker in _PRIVILEGE_ESCALATION_MARKERS:
        return "privilege_escalation"
    if marker in _PERSISTENCE_MARKERS:
        return "persistence_abuse"
    if marker in _STEALTH_MEMORY_MARKERS:
        return "stealth_memory_abuse"
    if marker in _KERNEL_MANIPULATION_MARKERS:
        return "kernel_manipulation"
    if marker in _RAW_DISK_ACCESS_MARKERS:
        return "raw_disk_access"
    if marker in _NETWORK_SPOOFING_MARKERS:
        return "network_spoofing"
    if marker in _REVERSE_ENGINEERING_MARKERS:
        return "reverse_engineering_abuse"
    return "defensive_only"


def _is_read_only_command(normalized_command: str) -> bool:
    compact = normalized_command.strip()
    if not compact:
        return False
    first = re.split(r"[\s|;&]+", compact, maxsplit=1)[0]
    return any(first == prefix or first.startswith(prefix) for prefix in _READONLY_COMMAND_PREFIXES)


def _parse_timeout(timeout_raw: object) -> int:
    try:
        timeout = int(timeout_raw)
    except (TypeError, ValueError):
        timeout = _DEFAULT_TIMEOUT_SECONDS
    return max(1, min(timeout, _MAX_TIMEOUT_SECONDS))


def _select_shell(command: str, shell_preference: str) -> tuple[list[str], str]:
    if shell_preference.strip():
        return _build_shell_command_preferred(command, shell_preference)
    return _build_shell_command(command)


def _is_within_root(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
        return True
    except ValueError:
        return False


def _resolve_cwd(params: dict[str, object]) -> str:
    cwd_param = params.get("cwd") or params.get("working_dir") or ""
    if cwd_param:
        cwd = resolve_user_path(str(cwd_param))[0]
    else:
        cwd = resolve_user_path(".")[0]

    root_override = bool(params.get("root_override", False))
    user_root = resolve_user_path(".")[0]
    if not root_override and not _is_within_root(cwd, user_root):
        raise PermissionError(f"cwd must stay under user root: {user_root}")
    return str(cwd)


def _blocked_response(analysis: dict[str, object]) -> str:
    category = str(analysis.get("blocked_category") or "defensive_only")
    guidance = _SAFE_GUIDANCE.get(category, _SAFE_GUIDANCE["defensive_only"])
    return (
        f"{guidance} Category: {category}. "
        f"Matched marker: {analysis['matched_defensive_marker']}"
    )


def _truncate_output(text: str, max_output: int) -> str:
    if len(text) <= max_output:
        return text
    return text[:max_output] + f"\n... (truncated to {max_output} chars)"


async def _run_shell(
    shell_argv: list[str],
    cwd: str,
    timeout: int,
) -> tuple[str, str, int]:
    env = os.environ.copy()
    env.setdefault("PYTHONIOENCODING", "utf-8")
    env.setdefault("PYTHONUTF8", "1")
    process = await asyncio.create_subprocess_exec(
        *shell_argv,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        cwd=cwd,
        env=env,
    )
    stdout_bytes, stderr_bytes = await asyncio.wait_for(process.communicate(), timeout=timeout)
    stdout = stdout_bytes.decode("utf-8", errors="replace")
    stderr = stderr_bytes.decode("utf-8", errors="replace")
    return stdout, stderr, process.returncode or 0


def _build_dry_run_payload(
    command: str,
    cwd: str,
    shell_name: str,
    timeout: int,
    analysis: dict[str, object],
) -> dict[str, object]:
    return {
        "dry_run": True,
        "command": command,
        "cwd": cwd,
        "shell": shell_name,
        "timeout": timeout,
        "risk_level": analysis["risk_level"],
        "needs_admin": analysis["needs_admin"],
        "read_only": analysis["read_only"],
        "command_quality": _build_command_quality(
            command=command,
            analysis=analysis,
            shell_name=shell_name,
            timeout=timeout,
            dry_run=True,
        ),
    }


def _build_command_quality(
    command: str,
    analysis: dict[str, object],
    shell_name: str,
    timeout: int,
    dry_run: bool,
) -> dict[str, object]:
    read_only = bool(analysis.get("read_only", False))
    safety = "readonly" if read_only else f"{analysis['risk_level']}"
    prerequisites: list[str] = [f"shell={shell_name}"]
    if bool(analysis.get("needs_admin", False)):
        prerequisites.append("admin-rights-may-be-required")
    return {
        "purpose": "Execute user-provided system command",
        "safety": safety,
        "prerequisites": prerequisites,
        "command": command,
        "expected_output": "exit_code=0 and no stderr for successful run",
        "failure_modes": [
            "permission_denied",
            "command_not_found",
            "timeout",
            "non_zero_exit",
        ],
        "next_step": "Inspect stdout/stderr and run targeted diagnostic command",
        "dry_run": dry_run,
        "timeout": timeout,
    }


class TerminalExecute(BaseTool):
    """Execute a shell command on the host OS."""

    name = "terminal_execute"
    description = (
        "Execute a shell command in a host working directory. "
        "Requires explicit user approval before running."
    )
    is_destructive = True  # always requires HITL approval

    async def execute(self, tool_input: ToolInput) -> ToolOutput:
        params = self._params(tool_input)
        command = str(self._first_param(params, "command", "cmd", "text", "value", default=""))
        if not command.strip():
            return self._failure("No command provided")

        analysis = _analyze_command(command)
        if bool(analysis["blocked_defensive_only"]):
            return self._failure(_blocked_response(analysis))
        if bool(analysis["blocked"]):
            return self._failure("Command blocked by safety policy (deny pattern matched)")

        timeout = _parse_timeout(params.get("timeout", _DEFAULT_TIMEOUT_SECONDS))

        dry_run = bool(params.get("dry_run", False))
        shell_preference = str(params.get("shell", "") or "")
        try:
            cwd = _resolve_cwd(params)
        except Exception as exc:
            return self._failure(str(exc))

        # Ensure working directory exists.
        os.makedirs(cwd, exist_ok=True)

        shell_argv, shell_name = _select_shell(command, shell_preference)

        if dry_run:
            return self._success(
                "Dry-run completed; command not executed",
                data=_build_dry_run_payload(command, cwd, shell_name, timeout, analysis),
            )

        logger.info("terminal.execute", command=command, cwd=cwd, timeout=timeout)

        try:
            stdout, stderr, exit_code = await _run_shell(shell_argv, cwd, timeout)

            # Truncate very long outputs to stay within LLM context limits.
            max_output = int(params.get("max_output_chars", 10_000))
            stdout = _truncate_output(stdout, max_output)
            stderr = _truncate_output(stderr, max_output)

            if exit_code != 0:
                return self._failure(
                    f"Command exited with code {exit_code}\nstdout:\n{stdout}\nstderr:\n{stderr}"
                )

            return self._success(
                f"Command completed (exit {exit_code})",
                data={
                    "stdout": stdout,
                    "stderr": stderr,
                    "exit_code": exit_code,
                    "shell": shell_name,
                    "risk_level": analysis["risk_level"],
                    "needs_admin": analysis["needs_admin"],
                    "read_only": analysis["read_only"],
                    "command_quality": _build_command_quality(
                        command=command,
                        analysis=analysis,
                        shell_name=shell_name,
                        timeout=timeout,
                        dry_run=False,
                    ),
                },
            )

        except TimeoutError:
            logger.warning("terminal.timeout", command=command, timeout=timeout)
            return self._failure(f"Command timed out after {timeout}s")
        except Exception as exc:
            return self._failure(str(exc))
