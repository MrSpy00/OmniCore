"""Communication Toolkit — email drafting via default mail client."""

from __future__ import annotations

import asyncio
from urllib.parse import quote
import webbrowser

from models.tools import ToolInput, ToolOutput
from tools.base import BaseTool


class CommSendEmail(BaseTool):
    name = "comm_send_email"
    description = "Open the default email client with a pre-filled draft."
    is_destructive = False

    async def execute(self, tool_input: ToolInput) -> ToolOutput:
        params = self._params(tool_input)
        to_addr = str(self._first_param(params, "to", "recipient", "email", default=""))
        subject = str(self._first_param(params, "subject", default="(no subject)"))
        body = str(self._first_param(params, "body", "text", "content", default=""))

        if not to_addr:
            return self._failure("recipient email is required")

        try:
            mailto = f"mailto:{quote(to_addr)}?subject={quote(subject)}&body={quote(body)}"
            await asyncio.to_thread(webbrowser.open, mailto)
            return self._success(
                "Mail draft opened",
                data={
                    "to": to_addr,
                    "subject": subject,
                    "body": body,
                    "mailto_url": mailto,
                },
            )
        except Exception as exc:
            return self._failure(str(exc))
