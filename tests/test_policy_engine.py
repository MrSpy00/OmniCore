"""Tests for capability policy governance rules."""

from __future__ import annotations

from core.policy import CapabilityPolicyEngine
from models.capabilities import RiskLevel
from models.tasks import TaskStep


class TestCapabilityPolicyEngine:
    def test_blocks_kernel_manipulation_category(self):
        engine = CapabilityPolicyEngine()
        step = TaskStep(
            tool_name="terminal_execute",
            description="attempt kernel probe",
            parameters={"command": (
                "bpftrace -e "
                "'tracepoint:syscalls:sys_enter_openat { printf(\"x\") }'"
            )},
            risk_level=RiskLevel.HIGH,
            dry_run_done=True,
        )
        decision = engine.evaluate(step)
        assert decision.allowed is False
        assert "kernel_manipulation_block" in decision.reasons
        assert decision.blocked_category == "kernel_manipulation"
        assert "kernel audit" in decision.safe_response.lower()

    def test_blocks_raw_disk_access_category(self):
        engine = CapabilityPolicyEngine()
        step = TaskStep(
            tool_name="terminal_execute",
            description="attempt raw disk read",
            parameters={"command": "type \\\\.\\PhysicalDrive0"},
            risk_level=RiskLevel.HIGH,
            dry_run_done=True,
        )
        decision = engine.evaluate(step)
        assert decision.allowed is False
        assert "raw_disk_access_block" in decision.reasons
        assert decision.blocked_category == "raw_disk_access"
        assert "forensic-safe" in decision.safe_response.lower()

    def test_blocks_network_spoofing_category(self):
        engine = CapabilityPolicyEngine()
        step = TaskStep(
            tool_name="terminal_execute",
            description="attempt isolated spoofing network",
            parameters={"command": "ip netns add ai_kapsulu"},
            risk_level=RiskLevel.HIGH,
            dry_run_done=True,
        )
        decision = engine.evaluate(step)
        assert decision.allowed is False
        assert "network_spoofing_block" in decision.reasons
        assert decision.blocked_category == "network_spoofing"
        assert "packet-capture" in decision.safe_response.lower()

    def test_blocks_reverse_engineering_abuse_category(self):
        engine = CapabilityPolicyEngine()
        step = TaskStep(
            tool_name="terminal_execute",
            description="attempt reverse analysis attach",
            parameters={"command": "cdb.exe -c \"bp User32!MessageBoxW; g\" app.exe"},
            risk_level=RiskLevel.HIGH,
            dry_run_done=True,
        )
        decision = engine.evaluate(step)
        assert decision.allowed is False
        assert "reverse_engineering_abuse_block" in decision.reasons
        assert decision.blocked_category == "reverse_engineering_abuse"
        assert "approved debugging" in decision.safe_response.lower()

    def test_blocks_stealth_memory_abuse_category(self):
        engine = CapabilityPolicyEngine()
        step = TaskStep(
            tool_name="terminal_execute",
            description="attempt fileless execution",
            parameters={"command": "python -c \"import os; os.memfd_create('gizli')\""},
            risk_level=RiskLevel.HIGH,
            dry_run_done=True,
        )
        decision = engine.evaluate(step)
        assert decision.allowed is False
        assert "stealth_memory_abuse_block" in decision.reasons
        assert decision.blocked_category == "stealth_memory_abuse"
        assert "memory telemetry" in decision.safe_response.lower()

    def test_blocks_privilege_escalation_category(self):
        engine = CapabilityPolicyEngine()
        step = TaskStep(
            tool_name="terminal_execute",
            description="attempt token escalation",
            parameters={"command": "whoami /priv && SeImpersonatePrivilege"},
            risk_level=RiskLevel.HIGH,
            dry_run_done=True,
        )
        decision = engine.evaluate(step)
        assert decision.allowed is False
        assert "privilege_escalation_block" in decision.reasons
        assert decision.blocked_category == "privilege_escalation"
        assert "least-privilege" in decision.safe_response.lower()

    def test_blocks_persistence_abuse_category(self):
        engine = CapabilityPolicyEngine()
        step = TaskStep(
            tool_name="terminal_execute",
            description="attempt WMI persistence",
            parameters={"command": (
                "wmic /namespace:\\root\\subscription "
                "PATH CommandLineEventConsumer CREATE"
            )},
            risk_level=RiskLevel.HIGH,
            dry_run_done=True,
        )
        decision = engine.evaluate(step)
        assert decision.allowed is False
        assert "persistence_abuse_block" in decision.reasons
        assert decision.blocked_category == "persistence_abuse"
        assert "persistence cleanup" in decision.safe_response.lower()

    def test_blocks_defensive_only_marker(self):
        engine = CapabilityPolicyEngine()
        step = TaskStep(
            tool_name="terminal_execute",
            description="attempt runtime hook",
            parameters={"command": "frida -U -f app.exe -l hook.js"},
            risk_level=RiskLevel.HIGH,
            dry_run_done=True,
        )
        decision = engine.evaluate(step)
        assert decision.allowed is False
        assert "defensive_only_block" in decision.reasons
        assert decision.blocked_category == "defensive_only"
        assert "detection" in decision.safe_response.lower()

    def test_blocks_deny_pattern(self):
        engine = CapabilityPolicyEngine()
        step = TaskStep(
            tool_name="terminal_execute",
            description="dangerous command",
            parameters={"command": "rm -rf /"},
            risk_level=RiskLevel.CRITICAL,
            dry_run_done=True,
            backup_ready=True,
        )
        decision = engine.evaluate(step)
        assert decision.allowed is False
        assert "command_matches_deny_pattern" in decision.reasons
        assert decision.blocked_category == "destructive"
        assert "irreversible risk" in decision.safe_response.lower()

    def test_high_requires_dry_run_and_confirmation(self):
        engine = CapabilityPolicyEngine()
        step = TaskStep(
            tool_name="os_write_file",
            description="write config",
            parameters={"path": "config.yaml", "content": "x"},
            risk_level=RiskLevel.HIGH,
            dry_run_done=False,
        )
        decision = engine.evaluate(step)
        assert decision.allowed is False
        assert decision.require_confirmation is True
        assert decision.require_dry_run is True
        assert "missing_dry_run" in decision.reasons

    def test_critical_requires_backup_and_double_confirmation(self):
        engine = CapabilityPolicyEngine()
        step = TaskStep(
            tool_name="process_kill",
            description="kill process",
            parameters={"pid": 1234},
            risk_level=RiskLevel.CRITICAL,
            dry_run_done=True,
            backup_ready=False,
        )
        decision = engine.evaluate(step)
        assert decision.allowed is False
        assert decision.require_double_confirmation is True
        assert decision.require_backup is True
        assert "backup_required" in decision.reasons
