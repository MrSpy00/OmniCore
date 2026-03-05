"""Communication Toolkit — email sending via SMTP."""

from __future__ import annotations

import smtplib
from email.message import EmailMessage

from models.tools import ToolInput, ToolOutput
from tools.base import BaseTool


class CommSendEmail(BaseTool):
    name = "comm_send_email"
    description = "Send an email via SMTP."
    is_destructive = True

    async def execute(self, tool_input: ToolInput) -> ToolOutput:
        smtp_host = tool_input.parameters.get("smtp_host", "")
        smtp_port = int(tool_input.parameters.get("smtp_port", 587))
        username = tool_input.parameters.get("username", "")
        password = tool_input.parameters.get("password", "")
        to_addr = tool_input.parameters.get("to", "")
        subject = tool_input.parameters.get("subject", "(no subject)")
        body = tool_input.parameters.get("body", "")

        if not smtp_host or not username or not password or not to_addr:
            return self._failure("smtp_host, username, password, and to are required")

        try:
            msg = EmailMessage()
            msg["From"] = username
            msg["To"] = to_addr
            msg["Subject"] = subject
            msg.set_content(body)

            with smtplib.SMTP(smtp_host, smtp_port, timeout=10) as server:
                server.starttls()
                server.login(username, password)
                server.send_message(msg)

            return self._success("Email sent", data={"to": to_addr})
        except Exception as exc:
            return self._failure(str(exc))
