from __future__ import annotations

from fastapi import APIRouter, File, Form, UploadFile

from lumberjack.api import chunk_to_dict, split_markdown_text

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


@router.post("/split")
async def split(
    text: str | None = Form(None),
    file: UploadFile | None = _file_default,
    max_tokens: int = Form(1200),
    min_tokens: int = Form(50),
    overlap_tokens: int = Form(0),
    retain_headings: bool = Form(True),
    merge_small_chunks: bool = Form(True),
    split_oversized_blocks: str = Form("paragraph,blockquote,html_block"),
    tokenizer: str = Form("simple"),
    document_title: str = Form("document.md"),
) -> dict:
    """Split Markdown text or an uploaded file into chunks and return JSON results."""
    if file is not None:
        content = (await file.read()).decode("utf-8")
        title = file.filename or document_title
    elif text is not None:
        content = text
        title = document_title
    else:
        return {"error": "Provide either markdown text or upload a file"}

    blocks = tuple(
        b.strip() for b in split_oversized_blocks.split(",") if b.strip() in _VALID_SPLIT_BLOCKS
    )

    chunks = split_markdown_text(
        content,
        document_title=title,
        max_tokens=max_tokens,
        min_tokens=min_tokens,
        overlap_tokens=overlap_tokens,
        retain_headings=retain_headings,
        merge_small_chunks=merge_small_chunks,
        split_oversized_blocks=blocks,
        tokenizer=tokenizer,
    )

    return {
        "document": title,
        "chunk_count": len(chunks),
        "chunks": [chunk_to_dict(c) for c in chunks],
    }
