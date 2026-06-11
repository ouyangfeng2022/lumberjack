from __future__ import annotations

import json
from dataclasses import asdict
from typing import Any

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from pydantic import BaseModel

from lumberjack import lumber
from lumberjack.core.models import BlockConfig

router = APIRouter()


class TextSplitRequest(BaseModel):
    text: str
    max_tokens: int = 1200
    ideal_max_tokens_ratio: float = 0.8
    merge_below_tokens: int = 50
    overlap_tokens: int = 0
    merge_small_chunks: bool = True
    skip_empty_sections: bool = True
    recursive_split: bool = False
    block_configs: dict[str, Any] | None = None
    tokenizer: str = "simple"
    splitter: str = "recursive"


class ChunkResponse(BaseModel):
    chunk_id: str
    chunk_type: str
    body: str
    token_count: int
    estimated_token_count: int
    headings: list[list[Any]]
    section_level: int
    document_title: str
    document_path: str | None
    start_line: int | None
    end_line: int | None


class SplitResponse(BaseModel):
    document: str
    chunk_count: int
    chunks: list[ChunkResponse]


_BLOCK_CONFIG_FIELDS = frozenset({"isolated", "split", "max_tokens"})


def _parse_block_configs(
    raw: dict[str, Any] | None,
) -> dict[str, BlockConfig] | None:
    if raw is None:
        return None

    resolved: dict[str, BlockConfig] = {}
    for kind, config in raw.items():
        if not isinstance(config, dict):
            raise HTTPException(
                status_code=400,
                detail=f"block_configs[{kind!r}] must be an object",
            )

        unknown = set(config) - _BLOCK_CONFIG_FIELDS
        if unknown:
            fields = ", ".join(sorted(_BLOCK_CONFIG_FIELDS))
            unknown_fields = ", ".join(sorted(unknown))
            raise HTTPException(
                status_code=400,
                detail=(
                    f"Unknown block config field(s) for {kind!r}: {unknown_fields}. "
                    f"Valid fields: {fields}"
                ),
            )

        try:
            resolved[kind] = BlockConfig(**config)
        except TypeError as e:
            raise HTTPException(status_code=400, detail=str(e)) from e

    return resolved


def _parse_form_block_configs(raw: str) -> dict[str, BlockConfig] | None:
    if not raw or not raw.strip():
        return None
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as e:
        raise HTTPException(status_code=400, detail="Invalid block_configs JSON") from e
    if not isinstance(parsed, dict):
        raise HTTPException(
            status_code=400, detail="block_configs must be a JSON object"
        )
    return _parse_block_configs(parsed)


@router.post("/split/text", response_model=SplitResponse)
async def split_text(payload: TextSplitRequest) -> SplitResponse:
    """Split Markdown text from a JSON request body into chunks."""
    block_options = _parse_block_configs(payload.block_configs)

    try:
        chunks = lumber(
            payload.text,
            max_tokens=payload.max_tokens,
            ideal_max_tokens_ratio=payload.ideal_max_tokens_ratio,
            merge_below_tokens=payload.merge_below_tokens,
            overlap_tokens=payload.overlap_tokens,
            merge_small_chunks=payload.merge_small_chunks,
            skip_empty_sections=payload.skip_empty_sections,
            recursive_split=payload.recursive_split,
            block_options=block_options,  # ty: ignore[invalid-argument-type]
            tokenizer=payload.tokenizer,
            splitter=payload.splitter,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e

    return SplitResponse(
        document=chunks[0].document_title if chunks else "Anonymous",
        chunk_count=len(chunks),
        chunks=[ChunkResponse(**asdict(c)) for c in chunks],
    )


def _detect_format_from_filename(filename: str) -> str:
    """Detect input format from file extension."""
    if filename and filename.lower().endswith(".docx"):
        return "docx"
    return "markdown"


@router.post("/split/file", response_model=SplitResponse)
async def split_file(
    file: UploadFile = File(...),  # noqa: B008
    input_format: str = Form("auto"),
    max_tokens: int = Form(1200),
    ideal_max_tokens_ratio: float = Form(0.8),
    merge_below_tokens: int = Form(50),
    overlap_tokens: int = Form(0),
    merge_small_chunks: bool = Form(True),
    skip_empty_sections: bool = Form(True),
    recursive_split: bool = Form(False),
    block_configs: str = Form(""),
    tokenizer: str = Form("simple"),
    splitter: str = Form("recursive"),
) -> SplitResponse:
    """Split an uploaded file (Markdown or DOCX) into chunks.

    The input format is auto-detected from the file extension when
    ``input_format`` is ``"auto"``.  Set it to ``"docx"`` or ``"markdown"``
    to override.
    """
    raw = await file.read()
    fmt = (
        input_format
        if input_format != "auto"
        else _detect_format_from_filename(file.filename or "")
    )

    if fmt == "docx":
        content = raw  # pass bytes directly to lumber()
    else:
        content = raw.decode("utf-8")

    block_options = _parse_form_block_configs(block_configs)

    try:
        chunks = lumber(
            content,
            format=fmt,
            document_title=file.filename,
            max_tokens=max_tokens,
            ideal_max_tokens_ratio=ideal_max_tokens_ratio,
            merge_below_tokens=merge_below_tokens,
            overlap_tokens=overlap_tokens,
            merge_small_chunks=merge_small_chunks,
            skip_empty_sections=skip_empty_sections,
            recursive_split=recursive_split,
            block_options=block_options,  # ty: ignore[invalid-argument-type]
            tokenizer=tokenizer,
            splitter=splitter,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e

    return SplitResponse(
        document=chunks[0].document_title if chunks else "Anonymous",
        chunk_count=len(chunks),
        chunks=[ChunkResponse(**asdict(c)) for c in chunks],
    )
