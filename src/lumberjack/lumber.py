from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from .core import create_splitter, create_tokenizer
from .core.markdown.parser import MarkdownItParser
from .core.models import BlockConfig, Chunk, SplitOptions

if TYPE_CHECKING:
    from .core.protocols import (
        MarkdownParserProtocol,
        SplitterProtocol,
        TokenizerProtocol,
    )


def _detect_format(text: str | bytes | Path, format: str) -> str:
    """Resolve the input format from the ``format`` hint and input type.

    Returns ``"docx"``, ``"html"``, or ``"markdown"``.
    """
    if format not in {"auto", "markdown", "docx", "html"}:
        msg = f"Unsupported input format: {format}"
        raise ValueError(msg)

    if format != "auto":
        return format

    if isinstance(text, bytes):
        # Raw bytes are treated as DOCX content
        return "docx"

    if isinstance(text, Path):
        ext = text.suffix.lower()
        if ext == ".docx":
            return "docx"
        if ext in {".html", ".htm"}:
            return "html"
        return "markdown"

    # Plain string is treated as Markdown text
    return "markdown"


def _read_input_for_markdown(text: str | bytes | Path) -> str:
    """Read markdown text from any input type."""
    if isinstance(text, Path):
        return text.read_text(encoding="utf-8")
    if isinstance(text, bytes):
        return text.decode("utf-8")
    return text


def _read_input_for_docx(text: str | bytes | Path) -> bytes:
    """Read DOCX binary content from any input type."""
    if isinstance(text, Path):
        return text.read_bytes()
    if isinstance(text, str):
        raise TypeError(
            "Expected bytes or a .docx file path for DOCX format, got a text string. "
            "Pass a Path or bytes instead."
        )
    return text


def lumber(
    text: str | bytes | Path = "",
    *,
    format: str = "auto",
    document_title: str | None = None,
    max_tokens: int = 1200,
    ideal_max_tokens_ratio: float = 0.8,
    merge_below_tokens: int | None = 50,
    skip_empty_sections: bool = True,
    recursive_split: bool = False,
    block_options: dict[str, BlockConfig | dict] | None = None,
    tokenizer: str | TokenizerProtocol = "simple",
    parser: MarkdownParserProtocol | None = None,
    splitter: str | SplitterProtocol = "recursive",
    document_metadata: dict[str, object] | None = None,
    max_heading_level: int | None = None,
) -> list[Chunk]:
    """Split a Markdown, HTML, or DOCX document into chunks recursively.

    Args:
        text: Document content as plain Markdown text, raw DOCX bytes,
            or a :class:`pathlib.Path` pointing to a ``.md``, ``.html``,
            or ``.docx`` file.
        format: Input format hint.  One of ``"auto"`` (the default),
            ``"markdown"``, ``"html"``, or ``"docx"``.  When ``"auto"``
            the format is inferred from the input type and/or file extension.
        document_title: Optional override for the document title.  When not
            provided the title is inferred from the document itself (front
            matter for Markdown, core properties for DOCX).
        max_tokens: Target maximum token count per chunk.
        ideal_max_tokens_ratio: Ratio of ``max_tokens`` used as the
            preferred split budget before post-processing merges.
        merge_below_tokens: Soft threshold for merging short tails. A negative
            value or ``None`` disables merging entirely; otherwise it must be
            smaller than ``max_tokens``.
        skip_empty_sections: Discard chunks containing only a heading
            with no body content when enabled.
        recursive_split: Enable block/text fallback for oversized
            section bodies (effective with ``--splitter section``).
        block_options: Per-block-kind :class:`BlockConfig` overrides.
        tokenizer: Tokenizer name or instance.
        parser: Custom text parser instance; ignored for DOCX input.
        splitter: Splitter name or instance.
        document_metadata: Extra metadata merged into the document.
        max_heading_level: Maximum heading level to parse as sections.
            Headings deeper than this level are treated as regular paragraphs.
            Applies to Markdown and HTML formats. If None, all headings are
            parsed.

    Returns:
        A list of :class:`Chunk` objects ready for downstream use.
    """
    input_format = _detect_format(text, format)

    # --- Tokenizer (shared) ---
    tokenizer_impl = (
        create_tokenizer(tokenizer) if isinstance(tokenizer, str) else tokenizer
    )

    # --- Parser (format-dependent) ---
    if input_format == "docx":
        from .core.docx import DocxParser

        raw = _read_input_for_docx(text)
        parser_impl = DocxParser()
        document = parser_impl.parse(
            raw,
            document_title=document_title,
            document_metadata=document_metadata,
        )
    else:
        raw = _read_input_for_markdown(text)
        if parser is not None:
            parser_impl = parser
        elif input_format == "html":
            from .core.html import HTMLParser

            parser_impl = HTMLParser()
        else:
            parser_impl = MarkdownItParser()
        document = parser_impl.parse(
            raw,
            document_title=document_title,
            document_metadata=document_metadata,
            max_heading_level=max_heading_level,
        )

    # --- Split options (shared) ---
    resolved = dict.fromkeys(sorted(parser_impl.block_kinds), BlockConfig())
    if block_options:
        for key, value in block_options.items():
            if isinstance(value, BlockConfig):
                resolved[key] = value
            elif isinstance(value, dict):
                resolved[key] = BlockConfig(**value)
            else:
                msg = f"block_options[{key!r}] must be BlockConfig or dict, got {type(value).__name__}"
                raise TypeError(msg)
    options = SplitOptions(
        max_tokens=max_tokens,
        ideal_max_tokens_ratio=ideal_max_tokens_ratio,
        merge_below_tokens=merge_below_tokens,
        skip_empty_sections=skip_empty_sections,
        recursive_split=recursive_split,
        block_options=resolved,
    )

    # --- Splitter (shared) ---
    splitter_impl = (
        create_splitter(splitter, tokenizer=tokenizer_impl, options=options)
        if isinstance(splitter, str)
        else splitter
    )
    return splitter_impl.split(document)


__all__ = ["lumber"]
