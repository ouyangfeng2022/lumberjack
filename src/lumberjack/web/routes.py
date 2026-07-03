from __future__ import annotations

from dataclasses import asdict
from typing import Any

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from pydantic import BaseModel

from lumberjack import lumber
from lumberjack.core.models import BaseParams
from lumberjack.core.options import parse_block_config_json, parse_block_config_mapping
from lumberjack.formats import detect_format_from_filename

router = APIRouter()


class TextSplitRequest(BaseModel):
    text: str
    input_format: str = "markdown"
    max_tokens: int = 1200
    ideal_max_tokens_ratio: float = 0.8
    merge_below_ratio: float = 0.125
    skip_empty_sections: bool = True
    render_headings: bool = True
    block_configs: dict[str, Any] | None = None
    tokenizer: str = "approx"
    splitter: str = "recursive"
    max_heading_level: int | None = None


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


def _parse_block_configs(
    raw: dict[str, Any] | None,
) -> dict[str, BaseParams] | None:
    try:
        return parse_block_config_mapping(raw)
    except (TypeError, ValueError) as e:
        raise HTTPException(status_code=400, detail=str(e)) from e


def _parse_form_block_configs(raw: str) -> dict[str, BaseParams] | None:
    if not raw or not raw.strip():
        return None
    try:
        return parse_block_config_json(raw)
    except (TypeError, ValueError) as e:
        raise HTTPException(status_code=400, detail=str(e)) from e


@router.post("/split/text", response_model=SplitResponse)
async def split_text(payload: TextSplitRequest) -> SplitResponse:
    """Split Markdown or HTML text from a JSON request body into chunks."""
    block_options = _parse_block_configs(payload.block_configs)

    try:
        chunks = lumber(
            payload.text,
            format=payload.input_format,
            max_tokens=payload.max_tokens,
            ideal_max_tokens_ratio=payload.ideal_max_tokens_ratio,
            merge_below_ratio=payload.merge_below_ratio,
            skip_empty_sections=payload.skip_empty_sections,
            render_headings=payload.render_headings,
            block_options=block_options,
            tokenizer=payload.tokenizer,
            splitter=payload.splitter,
            max_heading_level=payload.max_heading_level,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e

    return SplitResponse(
        document=chunks[0].document_title if chunks else "Anonymous",
        chunk_count=len(chunks),
        chunks=[ChunkResponse(**asdict(c)) for c in chunks],
    )


@router.post("/split/file", response_model=SplitResponse)
async def split_file(
    file: UploadFile = File(...),  # noqa: B008
    input_format: str = Form("auto"),
    max_tokens: int = Form(1200),
    ideal_max_tokens_ratio: float = Form(0.8),
    merge_below_ratio: float = Form(0.125),
    skip_empty_sections: bool = Form(True),
    render_headings: bool = Form(True),
    block_configs: str = Form(""),
    tokenizer: str = Form("approx"),
    splitter: str = Form("recursive"),
    max_heading_level: int | None = Form(None),
) -> SplitResponse:
    """Split an uploaded file (Markdown, HTML, or DOCX) into chunks.

    The input format is auto-detected from the file extension when
    ``input_format`` is ``"auto"``.  Set it to ``"docx"``, ``"html"``,
    or ``"markdown"`` to override.
    """
    raw = await file.read()
    fmt = (
        input_format
        if input_format != "auto"
        else detect_format_from_filename(file.filename or "")
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
            merge_below_ratio=merge_below_ratio,
            skip_empty_sections=skip_empty_sections,
            render_headings=render_headings,
            block_options=block_options,
            tokenizer=tokenizer,
            splitter=splitter,
            max_heading_level=max_heading_level,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e

    return SplitResponse(
        document=chunks[0].document_title if chunks else "Anonymous",
        chunk_count=len(chunks),
        chunks=[ChunkResponse(**asdict(c)) for c in chunks],
    )
