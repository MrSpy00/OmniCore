"""Document Toolkit — read PDF/DOCX files."""

from __future__ import annotations

import asyncio
from pathlib import Path

from models.tools import ToolInput, ToolOutput
from tools.base import BaseTool
from tools.base import resolve_user_path


def _resolve_sandboxed(path_str: str) -> Path:
    target, _ = resolve_user_path(path_str)
    return target


class DocReadPdf(BaseTool):
    name = "doc_read_pdf"
    description = "Extract text from a PDF or DOCX file on the host OS."

    async def execute(self, tool_input: ToolInput) -> ToolOutput:
        path = tool_input.parameters.get("path", "")
        if not path:
            return self._failure("path is required")

        try:
            target = _resolve_sandboxed(path)
            if target.suffix.lower() == ".pdf":
                from PyPDF2 import PdfReader

                text = await asyncio.to_thread(_read_pdf, target)
            elif target.suffix.lower() == ".docx":
                from docx import Document

                text = await asyncio.to_thread(_read_docx, target)
            else:
                return self._failure("Unsupported file type. Use PDF or DOCX.")

            max_chars = tool_input.parameters.get("max_chars", 20_000)
            if len(text) > max_chars:
                text = text[:max_chars] + "\n... (truncated)"

            return self._success("Document read", data={"text": text})
        except Exception as exc:
            return self._failure(str(exc))


def _read_pdf(path: Path) -> str:
    from PyPDF2 import PdfReader

    reader = PdfReader(str(path))
    return "\n".join(page.extract_text() or "" for page in reader.pages)


def _read_docx(path: Path) -> str:
    from docx import Document

    doc = Document(str(path))
    return "\n".join(p.text for p in doc.paragraphs)
