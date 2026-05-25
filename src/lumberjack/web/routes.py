from __future__ import annotations

from dataclasses import asdict

from fastapi import APIRouter, File, Form, HTTPException, UploadFile

from lumberjack.api import lumber
from lumberjack.models import SplitOptions

router = APIRouter()

_file_default = File(None)

_VALID_SPLIT_BLOCKS = frozenset(
    {
        "paragraph",
        "blockquote",
        "list",
        "table",
        "code_block",
        "code_fence",
        "html_block",
    }
)


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


def _parse_block_types(raw: str) -> frozenset[str]:
    """Parse a comma-separated block-type string into a validated frozenset."""
    return frozenset(
        b.strip() for b in raw.split(",") if b.strip() in _VALID_SPLIT_BLOCKS
    )


def _build_split_options(
    *,
    max_tokens: int,
    merge_below_tokens: int,
    overlap_tokens: int,
    render_common_headings: bool,
    merge_small_chunks: bool,
    isolate_front_matter: bool,
    skip_empty_sections: bool,
    recursive_split: bool,
    split_oversized_blocks: str,
    standalone_blocks: str,
) -> SplitOptions:
    """Build core split options from web form values."""
    return SplitOptions(
        max_tokens=max_tokens,
        merge_below_tokens=merge_below_tokens,
        overlap_tokens=overlap_tokens,
        render_common_headings=render_common_headings,
        merge_small_chunks=merge_small_chunks,
        isolate_front_matter=isolate_front_matter,
        skip_empty_sections=skip_empty_sections,
        recursive_split=recursive_split,
        split_oversized_blocks=_parse_block_types(split_oversized_blocks),
        standalone_blocks=_parse_block_types(standalone_blocks),
    )


@router.post("/split")
async def split(
    text: str | None = Form(None),
    file: UploadFile | None = _file_default,
    max_tokens: int = Form(1200),
    merge_below_tokens: int = Form(50),
    overlap_tokens: int = Form(0),
    render_common_headings: bool = Form(True),
    merge_small_chunks: bool = Form(True),
    isolate_front_matter: bool = Form(True),
    skip_empty_sections: bool = Form(True),
    recursive_split: bool = Form(False),
    split_oversized_blocks: str = Form("paragraph,blockquote,html_block"),
    standalone_blocks: str = Form("table,code_block,code_fence"),
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
        merge_below_tokens=merge_below_tokens,
        overlap_tokens=overlap_tokens,
        render_common_headings=render_common_headings,
        merge_small_chunks=merge_small_chunks,
        isolate_front_matter=isolate_front_matter,
        skip_empty_sections=skip_empty_sections,
        recursive_split=recursive_split,
        split_oversized_blocks=split_oversized_blocks,
        standalone_blocks=standalone_blocks,
    )

    try:
        chunks = lumber(
            content,
            document_title=document_title,
            max_tokens=options.max_tokens,
            merge_below_tokens=options.merge_below_tokens,
            overlap_tokens=options.overlap_tokens,
            render_common_headings=options.render_common_headings,
            merge_small_chunks=options.merge_small_chunks,
            isolate_front_matter=options.isolate_front_matter,
            skip_empty_sections=options.skip_empty_sections,
            split_oversized_blocks=options.split_oversized_blocks,
            standalone_blocks=options.standalone_blocks,
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
