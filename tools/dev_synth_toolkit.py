"""Dinamik Kod Sentezi Aracı — Mevcut araçların yetmediği durumlarda
göreve özel Python kodu üretip çalıştırır.
"""

from __future__ import annotations

from models.tools import ToolInput, ToolOutput
from tools.base import BaseTool


class DynamicCodeSynthesizeAndRun(BaseTool):
    """Mevcut araçların hiçbiri uymuyorsa göreve özel kod üretir ve çalıştırır."""

    name = "dynamic_code_synthesize"
    description = (
        "Generate and execute custom Python code for tasks not covered by existing tools. "
        "Code passes through AST safety filter before execution. Use only as last resort."
    )
    is_destructive = True

    async def execute(self, tool_input: ToolInput) -> ToolOutput:
        params = self._params(tool_input)
        task_description = str(
            self._first_param(params, "task", "description", "goal", "query") or ""
        )

        if not task_description:
            return self._failure("task parametresi gerekli — ne yapılmak istendiğini açıklayın.")

        try:
            from core.code_synth import DynamicCodeSynthesizer

            synthesizer = DynamicCodeSynthesizer(llm=None)
            result = await synthesizer.synthesize_and_execute(
                task_description=task_description,
                available_context={},
            )

            if result.get("success"):
                return self._success(
                    f"Kod başarıyla sentezlendi ve çalıştırıldı.\nSonuç: {result.get('result', '')}",
                    data={"code": result.get("code", ""), "result": result.get("result")},
                )
            else:
                errors = result.get("error", "Bilinmeyen hata")
                violations = result.get("violations", [])
                msg = f"Kod sentezi başarısız: {errors}"
                if violations:
                    msg += f"\nGüvenlik ihlalleri: {', '.join(violations)}"
                return self._failure(msg)
        except Exception as exc:
            return self._failure(f"Kod sentezi hatası: {exc}")
