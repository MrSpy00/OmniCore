"""Workflow Toolkit — advanced multi-step helper tools."""

from __future__ import annotations

import ast
import asyncio
import subprocess

from models.tools import ToolInput, ToolOutput
from tools.base import BaseTool
from tools.web_toolkit import _get_browser


class WorkflowSetAlarm(BaseTool):
    name = "workflow_set_alarm"
    description = "Set a local alarm by launching Windows clock or delayed beep."
    is_destructive = True

    async def execute(self, tool_input: ToolInput) -> ToolOutput:
        params = self._params(tool_input)
        seconds = int(self._first_param(params, "seconds", "delay", default=0) or 0)
        try:
            if seconds > 0:
                cmd = f"Start-Sleep -Seconds {seconds}; [console]::beep(1200,700)"
                await asyncio.to_thread(
                    subprocess.Popen,
                    ["powershell", "-NoProfile", "-Command", cmd],
                    shell=False,
                )
                return self._success(f"Alarm scheduled in {seconds} seconds")

            await asyncio.to_thread(
                subprocess.Popen,
                ["powershell", "-NoProfile", "-Command", "Start-Process ms-clock:"],
                shell=False,
            )
            return self._success("Opened Windows Clock app")
        except Exception as exc:
            return self._failure(str(exc))


class WorkflowSystemCalculator(BaseTool):
    name = "workflow_system_calculator"
    description = "Evaluate a math expression safely."

    async def execute(self, tool_input: ToolInput) -> ToolOutput:
        params = self._params(tool_input)
        expression = str(
            self._first_param(params, "expression", "expr", "query", "value", default="")
        )
        if not expression:
            return self._failure("expression is required")

        try:
            result = await asyncio.to_thread(_safe_eval_math, expression)
            return self._success(
                "Calculation completed", data={"expression": expression, "result": result}
            )
        except Exception as exc:
            return self._failure(str(exc))


class WebDeepScraper(BaseTool):
    name = "web_deep_scraper"
    description = "Use Playwright to navigate, dismiss cookie prompts, and extract array data."

    async def execute(self, tool_input: ToolInput) -> ToolOutput:
        params = self._params(tool_input)
        url = str(self._first_param(params, "url", "target", default=""))
        if not url:
            return self._failure("url is required")

        item_selector = str(self._first_param(params, "item_selector", default="a"))
        max_items = int(self._first_param(params, "max_items", default=25) or 25)
        cookie_selectors = params.get(
            "cookie_selectors",
            [
                "button#onetrust-accept-btn-handler",
                "button[aria-label='Accept all']",
                "button:has-text('Accept')",
                "button:has-text('I agree')",
            ],
        )
        if isinstance(cookie_selectors, str):
            cookie_selectors = [cookie_selectors]

        try:
            context = await _get_browser()
            page = await context.new_page()
            try:
                await page.goto(url, wait_until="domcontentloaded", timeout=30_000)
                for selector in cookie_selectors:
                    try:
                        await page.click(selector, timeout=1_500)
                        break
                    except Exception:
                        continue

                items = await page.evaluate(
                    """
                    ({ selector, maxItems }) => {
                        const nodes = Array.from(document.querySelectorAll(selector));
                        const values = [];
                        for (const n of nodes) {
                            const text = (n.innerText || n.textContent || '').trim();
                            if (text) values.push(text);
                            if (values.length >= maxItems) break;
                        }
                        return values;
                    }
                    """,
                    {"selector": item_selector, "maxItems": max_items},
                )
                body_text = await page.evaluate(
                    """
                    () => {
                        const scripts = document.querySelectorAll('script, style, noscript');
                        scripts.forEach(s => s.remove());
                        return document.body ? document.body.innerText : '';
                    }
                    """
                )
                return self._success(
                    "Deep scrape completed",
                    data={"url": url, "items": items, "content": body_text[:12000]},
                )
            finally:
                await page.close()
        except Exception as exc:
            return self._failure(str(exc))


def _safe_eval_math(expression: str) -> float:
    tree = ast.parse(expression, mode="eval")
    allowed = {
        ast.Expression,
        ast.BinOp,
        ast.UnaryOp,
        ast.Add,
        ast.Sub,
        ast.Mult,
        ast.Div,
        ast.FloorDiv,
        ast.Mod,
        ast.Pow,
        ast.USub,
        ast.UAdd,
        ast.Constant,
    }
    for node in ast.walk(tree):
        if type(node) not in allowed:
            raise ValueError("Unsupported expression")
    result = eval(compile(tree, "<expr>", "eval"), {"__builtins__": {}}, {})
    return float(result)
