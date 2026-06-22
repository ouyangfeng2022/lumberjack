from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import TYPE_CHECKING, cast

from .core.models import BlockConfig, Chunk, SplitOptions
from .core.options import resolve_block_options
from .core.parsers.factory import create_parser
from .core.splitters import create_splitter
from .core.tokenizers import create_tokenizer
from .formats import detect_format, read_docx_input, read_text_input

if TYPE_CHECKING:
    from .core.protocols import (
        ParserProtocol,
        SplitterProtocol,
        TokenizerProtocol,
    )


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
    block_options: Mapping[str, BlockConfig | dict] | None = None,
    tokenizer: str | TokenizerProtocol = "simple",
    parser: ParserProtocol[str] | ParserProtocol[bytes] | None = None,
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
        parser: Custom parser instance implementing :class:`ParserProtocol`.
            Overrides the default parser for the detected input format
            (Markdown, HTML, or DOCX). The parser must accept the input type
            produced for that format: ``str`` for Markdown/HTML, ``bytes`` for
            DOCX. A mismatch raises :class:`TypeError` from ``parse()``.
        splitter: Splitter name or instance.
        document_metadata: Extra metadata merged into the document.
        max_heading_level: Maximum heading level to parse as sections.
            Headings deeper than this level are treated as regular paragraphs.
            Applies to Markdown and HTML formats. If None, all headings are
            parsed.

    Returns:
        A list of :class:`Chunk` objects ready for downstream use.
    """
    input_format = detect_format(text, format)

    # --- Tokenizer (shared) ---
    tokenizer_impl = (
        create_tokenizer(tokenizer) if isinstance(tokenizer, str) else tokenizer
    )

    # --- Parser (format-dependent) ---
    # A user-supplied ``parser`` overrides the default for ANY format,
    # including DOCX. ``parse()`` is called with the unified signature.
    parser_impl = create_parser(input_format, parser=parser)
    if input_format == "docx":
        raw = read_docx_input(text)
        parser_impl = cast(ParserProtocol[bytes], parser_impl)
        document = parser_impl.parse(
            raw,
            document_title=document_title,
            document_metadata=document_metadata,
            max_heading_level=max_heading_level,
        )
    else:
        raw = read_text_input(text)
        parser_impl = cast(ParserProtocol[str], parser_impl)
        document = parser_impl.parse(
            raw,
            document_title=document_title,
            document_metadata=document_metadata,
            max_heading_level=max_heading_level,
        )

    # --- Split options (shared) ---
    resolved_block_options = resolve_block_options(parser_impl.block_kinds, block_options)
    options = SplitOptions(
        max_tokens=max_tokens,
        ideal_max_tokens_ratio=ideal_max_tokens_ratio,
        merge_below_tokens=merge_below_tokens,
        skip_empty_sections=skip_empty_sections,
        recursive_split=recursive_split,
        block_options=resolved_block_options,
    )

    # --- Splitter (shared) ---
    splitter_impl = (
        create_splitter(splitter, tokenizer=tokenizer_impl, options=options)
        if isinstance(splitter, str)
        else splitter
    )
    return splitter_impl.split(document)


__all__ = ["lumber"]
