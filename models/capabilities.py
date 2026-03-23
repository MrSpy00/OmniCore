"""Capability and policy models for risk-aware execution governance."""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, Field


class RiskLevel(StrEnum):
    """Standardized execution risk levels."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class CapabilityProfile(BaseModel):
    """Normalized capability profile resolved from tool + step context."""

    id: str
    domain: str
    action: str
    risk_level: RiskLevel = RiskLevel.MEDIUM
    requires_admin: bool = False
    dry_run_supported: bool = True


class PolicyDecision(BaseModel):
    """Policy evaluation output for a single execution step."""

    allowed: bool = True
    reasons: list[str] = Field(default_factory=list)
    blocked_category: str = ""
    safe_response: str = ""
    require_confirmation: bool = False
    require_double_confirmation: bool = False
    require_dry_run: bool = False
    require_backup: bool = False


class GovernancePolicy(BaseModel):
    """Default governance profile inspired by OmniCore capability packs."""

    deny_patterns: list[str] = Field(
        default_factory=lambda: [
            "rm -rf /",
            "format c:",
            "diskpart clean",
            "reg delete hklm\\system /f",
            "bcdedit /delete",
        ]
    )
    defensive_only_markers: list[str] = Field(
        default_factory=lambda: [
            "frida",
            "printspoofer",
            "roguewinrm",
            "fodhelper",
            "amsi bypass",
            "createremotethread",
            "writeprocessmemory",
            "etweventwrite",
            "syscall",
            "rootkit",
            "dns tunneling",
            "ip spoofing",
            "bpftrace",
            "psexec -s",
            "trustedinstaller",
        ]
    )
    privilege_escalation_markers: list[str] = Field(
        default_factory=lambda: [
            "seimpersonate",
            "nt authority\\system",
            "trustedinstaller",
            "psexec -s",
            "fodhelper",
            "uac bypass",
        ]
    )
    persistence_markers: list[str] = Field(
        default_factory=lambda: [
            "commandlineeventconsumer create",
            "\\root\\subscription",
            "currentversion\\run",
            "sc create",
            "autorun",
            "bootkit",
            "uefi",
        ]
    )
    stealth_memory_markers: list[str] = Field(
        default_factory=lambda: [
            "memfd_create",
            "execveat",
            "virtualallocex",
            "createremotethread",
            "writeprocessmemory",
            "reflection.assembly.load",
            "add-type -typedefinition",
            "ptrace",
            "rwx",
        ]
    )
    kernel_manipulation_markers: list[str] = Field(
        default_factory=lambda: [
            "ring 0",
            "kernel space",
            "bpftrace",
            "ebpf",
            "insmod",
            "rmmod",
            "sysrq-trigger",
        ]
    )
    raw_disk_access_markers: list[str] = Field(
        default_factory=lambda: [
            "\\\\.\\physicaldrive0",
            "mft parsing",
            "raw mft",
            "createfile(",
            "ntfsinfo",
            "vssadmin create shadow",
            "ntds.dit",
        ]
    )
    network_spoofing_markers: list[str] = Field(
        default_factory=lambda: [
            "sock_raw",
            "ip spoofing",
            "custom packet injection",
            "ip netns add",
            "ip netns exec",
            "nftables",
            "iptables",
        ]
    )
    reverse_engineering_markers: list[str] = Field(
        default_factory=lambda: [
            "windbg",
            "cdb.exe",
            "breakpoints",
            "int 3",
            "strace -f",
            "ltrace",
            "reverse engineering",
        ]
    )
    safe_response_templates: dict[str, str] = Field(
        default_factory=lambda: {
            "defensive_only": (
                "Request blocked by defensive-only policy. "
                "I can help with detection, prevention, hardening, and authorized "
                "remediation steps."
            ),
            "privilege_escalation": (
                "Privilege-escalation pattern blocked. "
                "I can help with least-privilege review, token hardening, and secure "
                "access remediation."
            ),
            "persistence_abuse": (
                "Persistence pattern blocked. "
                "I can help with startup/service/WMI audit, containment, and persistence "
                "cleanup playbook."
            ),
            "stealth_memory_abuse": (
                "Stealth memory-execution pattern blocked. "
                "I can help with memory telemetry, EDR hardening, and secure incident "
                "triage instead."
            ),
            "kernel_manipulation": (
                "Kernel-manipulation pattern blocked. "
                "I can help with kernel audit baselines, module allowlisting, and "
                "integrity monitoring."
            ),
            "raw_disk_access": (
                "Raw disk-access pattern blocked. "
                "I can help with forensic-safe acquisition planning and strict "
                "authorization controls."
            ),
            "network_spoofing": (
                "Network spoofing/injection pattern blocked. "
                "I can help with firewall validation, packet-capture diagnostics, and "
                "authorized network testing plans."
            ),
            "reverse_engineering_abuse": (
                "Reverse-engineering abuse pattern blocked. "
                "I can help with approved debugging workflows and safe observability "
                "instrumentation."
            ),
            "destructive": (
                "This action has irreversible risk. "
                "Use dry-run, backup, explicit confirmation, then execute staged validation."
            ),
        }
    )
