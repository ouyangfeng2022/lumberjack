from __future__ import annotations

import json
from dataclasses import asdict

from fastapi import APIRouter, File, Form, HTTPException, UploadFile

from lumberjack import lumber

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
    block_configs: str = Form(""),
    disable_lheading: bool = Form(False),
    tokenizer: str = Form("simple"),
    splitter: str = Form("recursive"),
) -> dict:
    """Split Markdown text or an uploaded file into chunks and return JSON results."""
    try:
        content, document_title = await _resolve_input(text, file)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e

    block_options = (
        json.loads(block_configs) if block_configs and block_configs.strip() else None
    )

    try:
        chunks = lumber(
            content,
            document_title=document_title,
            max_tokens=max_tokens,
            ideal_max_tokens_ratio=ideal_max_tokens_ratio,
            merge_below_tokens=merge_below_tokens,
            overlap_tokens=overlap_tokens,
            merge_small_chunks=merge_small_chunks,
            skip_empty_sections=skip_empty_sections,
            recursive_split=recursive_split,
            block_options=block_options,
            disable_lheading=disable_lheading,
            tokenizer=tokenizer,
            splitter=splitter,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e

    return {
        "document": chunks[0].document_title if chunks else "Anonymous",
        "chunk_count": len(chunks),
        "chunks": [asdict(c) for c in chunks],
    }
