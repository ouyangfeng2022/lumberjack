from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path

from .core.models import BaseParams, Chunk, SplitOptions
from .core.options import resolve_block_options
from .core.parsers import create_parser
from .core.splitters import create_splitter
from .core.tokenizers import create_tokenizer
from .formats import detect_format, read_docx_input, read_text_input


def lumber(
    text: str | bytes | Path = "",
    *,
    format: str = "auto",
    document_title: str | None = None,
    max_tokens: int = 1200,
    ideal_max_tokens_ratio: float = 0.8,
    merge_below_ratio: float = 0.125,
    skip_empty_sections: bool = True,
    render_headings: bool = True,
    block_options: Mapping[str, BaseParams | dict] | None = None,
    tokenizer: str = "approx",
    splitter: str = "recursive",
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
        merge_below_ratio: Tail-fragment merge threshold as a fraction of
            ``max_tokens`` in ``[0.0, 1.0)``.  Tail chunks below
            ``int(max_tokens * merge_below_ratio)`` tokens are merged into
            their same-heading predecessor when the result fits
            ``max_tokens``.  ``0.0`` disables merging entirely.
            Default ``0.125``.
        skip_empty_sections: Discard chunks containing only a heading
            with no body content when enabled.
        render_headings: When False, omit the chunk's ancestor heading
            breadcrumb from ``Chunk.body`` while keeping the chunk's own heading.
            See :attr:`SplitOptions.render_headings` for budget semantics.
        block_options: Per-block-kind :class:`BaseParams` overrides.
        tokenizer: Built-in tokenizer engine name (``"approx"``, ``"tiktoken"``,
            or ``"transformers"``). Independent of the splitter choice; any
            tokenizer works with any splitter.
        splitter: Built-in splitter name. ``"recursive"`` (default),
        ``"subtree"``, and ``"section"`` alias the exact (full-recount)
        variants; the explicit names ``"exact-recursive"``,
        ``"incremental-recursive"``, ``"exact-subtree"``,
        ``"incremental-subtree"``, ``"exact-section"``, and
        ``"incremental-section"`` select the counting strategy directly.
        ``subtree`` is subtree-first (collapses a fitting subtree into one
        chunk, with tail-fragment merging); ``section`` is per-heading, with
        no subtree-collapse and no tail-fragment merging.
        document_metadata: Extra metadata merged into the document.
        max_heading_level: Maximum heading level to keep as chunk section
            context. Headings deeper than this level are rendered as regular
            body text by the splitter. If None, all headings remain section
            context.

    Returns:
        A list of :class:`Chunk` objects ready for downstream use.
    """
    if not isinstance(tokenizer, str):
        raise TypeError(
            "tokenizer must be a string selecting a built-in tokenizer. "
            "For custom tokenizers, parse manually and pass the tokenizer "
            "instance to a splitter."
        )
    if not isinstance(splitter, str):
        raise TypeError(
            "splitter must be a string selecting a built-in splitter. "
            "For custom splitters, parse manually and call splitter.split()."
        )
    normalized_tokenizer = tokenizer.strip().lower()

    input_format = detect_format(text, format)

    tokenizer_impl = create_tokenizer(normalized_tokenizer)

    if input_format == "docx":
        parser_impl = create_parser("docx")
        raw = read_docx_input(text)
        document = parser_impl.parse(
            raw,
            document_title=document_title,
            document_metadata=document_metadata,
        )
    elif input_format == "html":
        parser_impl = create_parser("html")
        raw = read_text_input(text)
        document = parser_impl.parse(
            raw,
            document_title=document_title,
            document_metadata=document_metadata,
        )
    else:
        parser_impl = create_parser("markdown")
        raw = read_text_input(text)
        document = parser_impl.parse(
            raw,
            document_title=document_title,
            document_metadata=document_metadata,
        )

    resolved_block_options = resolve_block_options(
        parser_impl.block_kinds, block_options
    )
    options = SplitOptions(
        max_tokens=max_tokens,
        ideal_max_tokens_ratio=ideal_max_tokens_ratio,
        merge_below_ratio=merge_below_ratio,
        skip_empty_sections=skip_empty_sections,
        render_headings=render_headings,
        max_heading_level=max_heading_level,
        block_options=resolved_block_options,
    )

    splitter_impl = create_splitter(
        splitter,
        tokenizer=tokenizer_impl,
        options=options,
    )
    return splitter_impl.split(document)


__all__ = ["lumber"]
