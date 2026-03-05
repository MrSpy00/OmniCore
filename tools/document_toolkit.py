"""Document Toolkit — read PDF/DOCX files."""

from __future__ import annotations

from pathlib import Path

from config.settings import get_settings
from models.tools import ToolInput, ToolOutput
from tools.base import BaseTool


def _resolve_sandboxed(path_str: str) -> Path:
    sandbox = get_settings().sandbox_root.resolve()
    sandbox.mkdir(parents=True, exist_ok=True)
    target = (sandbox / path_str).resolve()
    if not str(target).startswith(str(sandbox)):
        raise PermissionError(f"Path '{target}' escapes sandbox root '{sandbox}'")
    return target


class DocReadPdf(BaseTool):
    name = "doc_read_pdf"
    description = "Extract text from a PDF or DOCX file in the sandbox."

    async def execute(self, tool_input: ToolInput) -> ToolOutput:
        path = tool_input.parameters.get("path", "")
        if not path:
            return self._failure("path is required")

        try:
            target = _resolve_sandboxed(path)
            if target.suffix.lower() == ".pdf":
                from PyPDF2 import PdfReader

                reader = PdfReader(str(target))
                text = "\n".join(page.extract_text() or "" for page in reader.pages)
            elif target.suffix.lower() == ".docx":
                from docx import Document

                doc = Document(str(target))
                text = "\n".join(p.text for p in doc.paragraphs)
            else:
                return self._failure("Unsupported file type. Use PDF or DOCX.")

            max_chars = tool_input.parameters.get("max_chars", 20_000)
            if len(text) > max_chars:
                text = text[:max_chars] + "\n... (truncated)"

            return self._success("Document read", data={"text": text})
        except Exception as exc:
            return self._failure(str(exc))
