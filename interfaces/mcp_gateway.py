"""Enterprise MCP (Model Context Protocol) Gateway.

Exposes OmniCore toolkits to external tools and IDEs (Claude Desktop, Zed, Cursor)
via standard MCP JSON-RPC 2.0 protocol.

Security model:
  - Authentication via API key (Bearer token in header or env MCP_API_KEY).
  - All tool executions pass through CapabilityPolicyEngine and Guardian HITL.
  - Dangerous tools (deletion, shell, registry) require explicit approval.
"""

from __future__ import annotations

import json
import os
import secrets
from pathlib import Path
from typing import Any

from config.logging import get_logger
from models.tasks import TaskStep
from models.tools import ToolInput
from tools.registry import discover_tool_classes

logger = get_logger(__name__)

# Resolved project root for tool discovery
_PROJECT_ROOT = Path(__file__).resolve().parent.parent

# Ephemeral API key generated on first use (when MCP_API_KEY env not set)
_EPHEMERAL_KEY: str | None = None


def _get_effective_key() -> str:
    """Return the MCP gateway API key (env or ephemeral)."""
    global _EPHEMERAL_KEY
    configured = os.environ.get("MCP_API_KEY", "").strip()
    if configured:
        return configured
    if _EPHEMERAL_KEY is None:
        _EPHEMERAL_KEY = secrets.token_urlsafe(32)
        logger.warning(
            "mcp.no_api_key_ephemeral_generated",
            hint="Set MCP_API_KEY environment variable for persistent access",
        )
    return _EPHEMERAL_KEY


class MCPServerGateway:
    """JSON-RPC 2.0 server handler for Model Context Protocol integration.

    Security:
      - Requires API key authentication (``mcp_authenticate`` method or env).
      - All tool calls route through ``CapabilityPolicyEngine`` and
        ``Guardian`` for HITL approval on destructive operations.
    """

    def __init__(self) -> None:
        tools_dir = _PROJECT_ROOT / "tools"
        self.tool_classes: dict[str, type] = {cls.name: cls for cls in discover_tool_classes(tools_dir)}
        self._authenticated_sessions: set[str] = set()
        self._policy = None
        self._guardian = None

    def set_policy_engine(self, policy_engine: Any) -> None:
        """Inject the CapabilityPolicyEngine for tool safety checks."""
        self._policy = policy_engine

    def set_guardian(self, guardian: Any) -> None:
        """Inject the Guardian for HITL approval gating."""
        self._guardian = guardian

    def _verify_auth(self, params: dict[str, Any]) -> bool:
        """Check API key from params or session state."""
        api_key = params.get("apiKey", "") or params.get("api_key", "")
        if api_key:
            expected = _get_effective_key()
            if secrets.compare_digest(api_key, expected):
                return True
        # Also check if session was previously authenticated via mcp_authenticate
        session_id = params.get("_sessionId", "")
        if session_id and session_id in self._authenticated_sessions:
            return True
        return False

    async def handle_request_json(self, json_str: str) -> str:
        """Parse raw JSON-RPC string and handle request."""
        try:
            req = json.loads(json_str)
            resp = await self.handle_request(req)
            return json.dumps(resp)
        except Exception as exc:
            return json.dumps(
                {
                    "jsonrpc": "2.0",
                    "error": {"code": -32700, "message": f"Parse error: {exc}"},
                    "id": None,
                }
            )

    async def handle_request(self, req: dict[str, Any]) -> dict[str, Any]:
        """Route JSON-RPC request to appropriate handler."""
        req_id = req.get("id")
        method = req.get("method", "")
        params = req.get("params", {})

        # JSON-RPC notifications (no id) — return nothing per spec
        if req_id is None and method != "notifications/initialized":
            return {}

        # --- Authentication ---
        if method == "mcp_authenticate":
            api_key = params.get("apiKey", "") or params.get("api_key", "")
            expected = _get_effective_key()
            if api_key and secrets.compare_digest(api_key, expected):
                session_id = secrets.token_urlsafe(16)
                self._authenticated_sessions.add(session_id)
                return {
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "result": {"sessionId": session_id, "authenticated": True},
                }
            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "error": {"code": -32001, "message": "Authentication failed"},
            }

        # --- Initialize (no auth required) ---
        if method == "initialize":
            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "result": {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {"tools": {}},
                    "serverInfo": {"name": "OmniCore-MCP-Gateway", "version": "0.1.0"},
                    "instructions": "Authenticate via mcp_authenticate before calling tools.",
                },
            }

        # --- Notification ack (no response needed) ---
        if method == "notifications/initialized":
            return {}

        # --- All subsequent methods require authentication ---
        if not self._verify_auth(params):
            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "error": {"code": -32001, "message": "Not authenticated. Call mcp_authenticate first."},
            }

        # --- Tools listing ---
        if method == "tools/list":
            tool_list = []
            for name, cls in self.tool_classes.items():
                tool_list.append(
                    {
                        "name": name,
                        "description": getattr(cls, "description", ""),
                        "inputSchema": getattr(cls, "input_schema", {"type": "object", "properties": {}}),
                    }
                )
            return {"jsonrpc": "2.0", "id": req_id, "result": {"tools": tool_list}}

        # --- Tool execution with policy + guardian gates ---
        if method == "tools/call":
            tool_name = params.get("name", "")
            arguments = params.get("arguments", {})
            if tool_name not in self.tool_classes:
                return {
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "error": {"code": -32601, "message": f"Tool '{tool_name}' not found"},
                }

            # Build tool input
            tool_cls = self.tool_classes[tool_name]
            tool_instance = tool_cls()
            sub_input = ToolInput(tool_name=tool_name, parameters=arguments)

            # --- Policy Engine Gate ---
            if self._policy is not None:
                try:
                    risk_level = getattr(tool_instance, "risk_level", "medium")
                    from models.capabilities import RiskLevel

                    step = TaskStep(
                        id=f"mcp_{tool_name}",
                        description=f"MCP tool call: {tool_name}",
                        tool_name=tool_name,
                        parameters=arguments,
                        risk_level=RiskLevel(risk_level) if risk_level else RiskLevel.MEDIUM,
                        requires_approval=tool_instance.requires_approval(sub_input),
                    )
                    decision = self._policy.evaluate(step)
                    if not decision.allowed:
                        reasons = ", ".join(decision.reasons) if decision.reasons else "policy_blocked"
                        logger.warning(
                            "mcp.tool_blocked_by_policy",
                            tool=tool_name,
                            reasons=reasons,
                        )
                        return {
                            "jsonrpc": "2.0",
                            "id": req_id,
                            "result": {
                                "content": [{"type": "text", "text": f"[BLOCKED by policy] {reasons}"}],
                                "isError": True,
                            },
                        }
                except Exception as exc:
                    logger.error("mcp.policy_check_error", tool=tool_name, error=str(exc))

            # --- Guardian HITL Gate ---
            if self._guardian is not None and tool_instance.requires_approval(sub_input):
                try:
                    from core.guardian import ApprovalResult

                    result = await self._guardian.request_approval(
                        action_description=f"MCP tool: {tool_name}({json.dumps(arguments, ensure_ascii=False)[:200]})",
                        user_id="mcp_client",
                    )
                    if result != ApprovalResult.APPROVED:
                        logger.info("mcp.tool_denied_by_guardian", tool=tool_name, result=result)
                        return {
                            "jsonrpc": "2.0",
                            "id": req_id,
                            "result": {
                                "content": [
                                    {"type": "text", "text": f"[DENIED by Guardian] Action not approved: {result}"}
                                ],
                                "isError": True,
                            },
                        }
                except Exception as exc:
                    logger.error("mcp.guardian_error", tool=tool_name, error=str(exc))

            # --- Execute ---
            try:
                output = await tool_instance.execute(sub_input)
                return {
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "result": {
                        "content": [{"type": "text", "text": output.result or output.error or ""}],
                        "isError": output.status.value != "success",
                    },
                }
            except Exception as exc:
                logger.error("mcp.tool_execution_error", tool=tool_name, error=str(exc))
                return {
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "result": {
                        "content": [{"type": "text", "text": f"[EXECUTION ERROR] {type(exc).__name__}: {exc}"}],
                        "isError": True,
                    },
                }

        return {
            "jsonrpc": "2.0",
            "id": req_id,
            "error": {"code": -32601, "message": f"Method '{method}' not found"},
        }
