"""PDF parsing through local MarkItDown conversion."""

from __future__ import annotations

from io import BytesIO
from pathlib import Path
from typing import ClassVar

from markitdown import MarkItDown
from pdfplumber import open as open_pdf

from ...models import DocTree, Document
from ..markdown import MarkdownParser


class PdfParser:
    """Convert a text-layer PDF to Markdown, then parse the Markdown tree.

    Plugins are disabled so parsing stays local and never uploads document data.
    Scanned PDFs are outside Lumberjack's scope; use MinerU or PaddleOCR.
    """

    block_kinds: ClassVar[frozenset[str]] = MarkdownParser().block_kinds

    def parse(
        self,
        document: Document | bytes,
        *,
        document_title: str | None = None,
        metadata_overrides: dict[str, object] | None = None,
        source_path: str | Path | None = None,
    ) -> DocTree:
        if not isinstance(document, Document):
            document = Document(
                document,
                format="pdf",
                document_title=document_title,
                metadata_overrides=dict(metadata_overrides or {}),
                source_path=source_path,
            )
        if not isinstance(document.source, bytes | bytearray):
            raise TypeError("PdfParser.parse expects Document[bytes]")
        try:
            # MarkItDown falls back to its plain-text converter for malformed
            # PDFs, which would emit the PDF bytes as document content.
            with open_pdf(BytesIO(bytes(document.source))):
                pass
            markdown = (
                MarkItDown(enable_plugins=False)
                .convert_stream(BytesIO(bytes(document.source)), file_extension=".pdf")
                .markdown.strip()
            )
        except Exception as exc:
            raise ValueError(f"Invalid or unreadable PDF: {exc}") from exc
        if not markdown:
            raise ValueError(
                "PDF contains no extractable text; use MinerU or PaddleOCR for scanned PDFs"
            )
        return MarkdownParser().parse(
            Document(
                markdown,
                format="markdown",
                document_title=document.document_title,
                metadata_overrides=dict(document.metadata_overrides),
                source_path=document.source_path,
            )
        )
