"""Browser Enhanced Toolkit — incognito mode, persistent contexts, and browser lifecycle."""

from __future__ import annotations

from models.tools import ToolInput, ToolOutput
from tools.base import BaseTool


class BrowserIncognito(BaseTool):
    """Browse a URL in incognito/private mode with no history or cookies."""

    name = "browser_incognito"
    description = (
        "Open a URL in incognito/private browsing mode. No cookies, history, "
        "or cache are saved. Parameters: url (required)."
    )
    is_destructive = False

    async def execute(self, tool_input: ToolInput) -> ToolOutput:
        params = self._params(tool_input)
        url = str(self._first_param(params, "url", "link", default="") or "").strip()
        if not url:
            return self._failure("url parameter is required.")
        if not url.startswith(("http://", "https://")):
            url = f"https://{url}"

        try:
            from playwright.async_api import async_playwright

            async with async_playwright() as pw:
                browser = await pw.chromium.launch(headless=True)
                context = await browser.new_context(
                    no_viewport=False,
                    user_agent=(
                        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                        "AppleWebKit/537.36 (KHTML, like Gecko) "
                        "Chrome/131.0.0.0 Safari/537.36"
                    ),
                )
                page = await context.new_page()
                response = await page.goto(url, wait_until="domcontentloaded", timeout=30000)
                title = await page.title()
                content = await page.inner_text("body")
                await browser.close()

            status = response.status if response else 0
            return self._success(
                f"Incognito page loaded: {title}",
                data={
                    "url": url,
                    "title": title,
                    "status": status,
                    "content": content[:5000],
                    "mode": "incognito",
                },
            )
        except Exception as exc:
            return self._failure(f"Incognito browse failed: {exc}")


class BrowserManageContext(BaseTool):
    """Manage persistent browser contexts for multi-step browsing."""

    name = "browser_manage_context"
    description = (
        "Create, list, or destroy browser contexts for persistent sessions. "
        "Parameters: action (create|list|close), context_id (for close)."
    )
    is_destructive = False

    _contexts: dict[str, object] = {}

    async def execute(self, tool_input: ToolInput) -> ToolOutput:
        params = self._params(tool_input)
        action = str(self._first_param(params, "action", default="list")).lower()
        context_id = str(self._first_param(params, "context_id", "id", default="") or "")

        if action == "list":
            return self._success(
                "Active contexts",
                data={"contexts": list(self._contexts.keys()), "count": len(self._contexts)},
            )

        if action == "close":
            if context_id and context_id in self._contexts:
                ctx = self._contexts.pop(context_id)
                try:
                    await ctx.close()  # type: ignore
                except Exception:
                    pass
                return self._success(f"Context {context_id} closed")
            return self._failure(f"Context {context_id} not found")

        return self._failure(f"Unknown action: {action}. Use create, list, or close.")
