from __future__ import annotations

from dataclasses import asdict

from fastapi import APIRouter, File, Form, HTTPException, UploadFile

from lumberjack import lumber
from lumberjack.core.models import BlockHandling, SplitOptions
from lumberjack.core.parser import MarkdownItParser

router = APIRouter()

_file_default = File(None)


async def _resolve_input(
    text: str | None,
    file: UploadFile | None,
) -> tuple[str, str]:
    """Resolve text/file input into (content, title), or None if both are missing."""
    if file is not None:
        content = (await file.read()).decode("utf-8")
        return content, file.filename
    if text is not None:
        return text, None
    raise ValueError("Provide either markdown text or upload a file")


def _parse_block_handling(raw: str) -> dict[str, BlockHandling]:
    """Parse a comma-separated ``kind:policy`` string into a validated dict.

    Returns the default handling merged with any overrides from *raw*.
    """
    result = dict(MarkdownItParser.default_registry().default_handling())
    if not raw or not raw.strip():
        return result
    for part in raw.split(","):
        part = part.strip()
        if not part or ":" not in part:
            raise ValueError(
                f"Invalid format: {part!r} (expected kind:policy, e.g. table:isolate)"
            )
        kind, _, value = part.partition(":")
        kind = kind.strip().lower()
        value = value.strip().lower()
        MarkdownItParser.default_registry().validate_kind(kind)
        if not value:
            raise ValueError(f"Missing policy in: {part!r} (expected kind:policy)")
        try:
            result[kind] = BlockHandling(value)
        except ValueError:
            valid = ", ".join(h.value for h in BlockHandling)
            raise ValueError(
                f"Invalid policy in: {part!r} (valid policies: {valid})"
            ) from None
    return result


def _parse_nosplit_kinds(raw: str) -> frozenset[str]:
    """Parse a comma-separated string of block kinds into a frozenset."""
    if not raw or not raw.strip():
        return frozenset()
    kinds: set[str] = set()
    for part in raw.split(","):
        kind = part.strip().lower()
        if not kind:
            continue
        MarkdownItParser.default_registry().validate_kind(kind)
        kinds.add(kind)
    return frozenset(kinds)


def _parse_block_max_tokens(raw: str) -> dict[str, int]:
    """Parse a comma-separated ``kind:tokens`` string into a validated dict."""
    result: dict[str, int] = {}
    if not raw or not raw.strip():
        return result
    for part in raw.split(","):
        part = part.strip()
        if not part or ":" not in part:
            raise ValueError(
                f"Invalid format: {part!r} (expected kind:tokens, e.g. paragraph:800)"
            )
        kind, _, value = part.partition(":")
        kind = kind.strip().lower()
        tokens_str = value.strip()
        MarkdownItParser.default_registry().validate_kind(kind)
        if not tokens_str:
            raise ValueError(f"Missing token count in: {part!r} (expected kind:tokens)")
        try:
            tokens = int(tokens_str)
        except ValueError:
            raise ValueError(
                f"Invalid token count in: {part!r} (expected kind:tokens)"
            ) from None
        if tokens <= 0:
            raise ValueError(f"Token count must be positive in: {part!r}")
        result[kind] = tokens
    return result


def _build_split_options(
    *,
    max_tokens: int,
    ideal_max_tokens_ratio: float,
    merge_below_tokens: int,
    overlap_tokens: int,
    merge_small_chunks: bool,
    skip_empty_sections: bool,
    recursive_split: bool,
    block_handling: str,
    block_max_tokens: str,
    nosplit_kinds: str,
) -> SplitOptions:
    """Build core split options from web form values."""
    return SplitOptions(
        max_tokens=max_tokens,
        ideal_max_tokens_ratio=ideal_max_tokens_ratio,
        merge_below_tokens=merge_below_tokens,
        overlap_tokens=overlap_tokens,
        merge_small_chunks=merge_small_chunks,
        skip_empty_sections=skip_empty_sections,
        recursive_split=recursive_split,
        block_handling=_parse_block_handling(block_handling),
        nosplit_kinds=_parse_nosplit_kinds(nosplit_kinds),
        block_max_tokens=_parse_block_max_tokens(block_max_tokens),
    )


@router.post("/split")
async def split(
    text: str | None = Form(None),
    file: UploadFile | None = _file_default,
    max_tokens: int = Form(1200),
    ideal_max_tokens_ratio: float = Form(0.8),
    merge_below_tokens: int = Form(50),
    overlap_tokens: int = Form(0),
    merge_small_chunks: bool = Form(True),
    skip_empty_sections: bool = Form(True),
    recursive_split: bool = Form(False),
    block_handling: str = Form(""),
    block_max_tokens: str = Form(""),
    nosplit_kinds: str = Form(""),
    disable_lheading: bool = Form(False),
    tokenizer: str = Form("simple"),
    splitter: str = Form("recursive"),
) -> dict:
    """Split Markdown text or an uploaded file into chunks and return JSON results."""
    try:
        content, document_title = await _resolve_input(text, file)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e

    options = _build_split_options(
        max_tokens=max_tokens,
        ideal_max_tokens_ratio=ideal_max_tokens_ratio,
        merge_below_tokens=merge_below_tokens,
        overlap_tokens=overlap_tokens,
        merge_small_chunks=merge_small_chunks,
        skip_empty_sections=skip_empty_sections,
        recursive_split=recursive_split,
        block_handling=block_handling,
        block_max_tokens=block_max_tokens,
        nosplit_kinds=nosplit_kinds,
    )

    try:
        chunks = lumber(
            content,
            document_title=document_title,
            max_tokens=options.max_tokens,
            ideal_max_tokens_ratio=options.ideal_max_tokens_ratio,
            merge_below_tokens=options.merge_below_tokens,
            overlap_tokens=options.overlap_tokens,
            merge_small_chunks=options.merge_small_chunks,
            skip_empty_sections=options.skip_empty_sections,
            block_handling=options.block_handling,
            nosplit_kinds=options.nosplit_kinds,
            block_max_tokens=options.block_max_tokens,
            disable_lheading=disable_lheading,
            tokenizer=tokenizer,
            splitter=splitter,
            recursive_split=options.recursive_split,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e

    return {
        "document": chunks[0].document_title if chunks else "Anonymous",
        "chunk_count": len(chunks),
        "chunks": [asdict(c) for c in chunks],
    }
