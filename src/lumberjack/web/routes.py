from __future__ import annotations

from dataclasses import asdict
from typing import Any, Literal, cast

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from pydantic import BaseModel
from pydantic import Field as PydanticField

from lumberjack._internal.formats import detect_format_from_filename
from lumberjack._internal.options import (
    parse_block_config_json,
    parse_block_config_mapping,
)
from lumberjack._internal.pipeline import TokenizerRegistry, split_source, trace_source
from lumberjack._internal.trace import TraceStage, select_trace_stages
from lumberjack.block import BlockOption
from lumberjack.models import SourceLocation
from lumberjack.parser import InputFormat

router = APIRouter()
_TOKENIZERS = TokenizerRegistry()

TokenizerName = Literal["approx", "tiktoken", "transformers"]
SplitterName = Literal[
    "sibling",
    "exact-sibling",
    "incremental-sibling",
    "subtree",
    "exact-subtree",
    "incremental-subtree",
    "section",
    "exact-section",
    "incremental-section",
    "record",
]


class TextSplitRequest(BaseModel):
    text: str
    input_format: Literal[
        "markdown",
        "html",
        "text",
        "log",
        "csv",
        "tsv",
        "json",
        "jsonl",
        "xml",
        "yaml",
        "toml",
        "sql",
        "python",
        "javascript",
        "typescript",
        "notebook",
    ] = "markdown"
    max_tokens: int = PydanticField(1200, gt=0)
    ideal_max_tokens_ratio: float = PydanticField(0.8, gt=0, le=1)
    merge_below_ratio: float = PydanticField(0.125, ge=0, lt=1)
    skip_empty_sections: bool = True
    heading_sensitive: bool = True
    block_configs: dict[str, Any] | None = None
    tokenizer: TokenizerName = PydanticField(
        "approx",
        description="Tokenizer engine used only to encode and count text.",
    )
    splitter: SplitterName = PydanticField(
        "section",
        description=(
            "Splitter topology and counting mode. Unprefixed names use "
            "incremental measurement; exact-* names fully recount candidates."
        ),
    )
    max_heading_level: int | None = PydanticField(None, ge=0)
    trace_stages: list[TraceStage] = PydanticField(default_factory=list)
    trace_max_bytes: int = PydanticField(1_048_576, gt=0, le=10_485_760)


class ChunkResponse(BaseModel):
    chunk_id: str
    chunk_type: str
    body: str
    token_count: int
    estimated_token_count: int
    headings_token_count: int
    body_token_count: int
    ancestor_headings: list[tuple[int, str]]
    own_heading: tuple[int, str] | None
    section_level: int
    document_title: str
    document_path: str | None
    start_line: int | None
    end_line: int | None
    source_locations: list[SourceLocation]
    protected: bool


class SplitResponse(BaseModel):
    document: str
    metadata: dict[str, Any]
    reference_definitions: dict[str, dict[str, str]]
    chunk_count: int
    chunks: list[ChunkResponse]
    trace: dict[str, Any] | None = None


def _pipeline_http_error(error: Exception) -> HTTPException:
    if isinstance(error, (ImportError, UnicodeDecodeError, ValueError)):
        return HTTPException(status_code=400, detail=str(error))
    return HTTPException(status_code=500, detail="Internal split pipeline error")


def _parse_block_configs(
    raw: dict[str, Any] | None,
) -> list[BlockOption] | None:
    try:
        return parse_block_config_mapping(raw)
    except (TypeError, ValueError) as e:
        raise HTTPException(status_code=400, detail=str(e)) from e


def _parse_form_block_configs(raw: str) -> list[BlockOption] | None:
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
        tokenizer = _TOKENIZERS.create(payload.tokenizer)
        trace_payload: dict[str, object] | None = None
        if payload.trace_stages:
            trace = trace_source(
                payload.text,
                format=payload.input_format,
                max_tokens=payload.max_tokens,
                ideal_max_tokens_ratio=payload.ideal_max_tokens_ratio,
                merge_below_ratio=payload.merge_below_ratio,
                skip_empty_sections=payload.skip_empty_sections,
                heading_sensitive=payload.heading_sensitive,
                block_options=block_options,
                tokenizer=tokenizer,
                splitter=payload.splitter,
                max_heading_level=payload.max_heading_level,
            )
            result_document = trace.document
            result_chunks = trace.chunks
            trace_payload = select_trace_stages(
                trace,
                payload.trace_stages,
                max_bytes=payload.trace_max_bytes,
            )
        else:
            result = split_source(
                payload.text,
                format=payload.input_format,
                max_tokens=payload.max_tokens,
                ideal_max_tokens_ratio=payload.ideal_max_tokens_ratio,
                merge_below_ratio=payload.merge_below_ratio,
                skip_empty_sections=payload.skip_empty_sections,
                heading_sensitive=payload.heading_sensitive,
                block_options=block_options,
                tokenizer=tokenizer,
                splitter=payload.splitter,
                max_heading_level=payload.max_heading_level,
            )
            result_document = result.document
            result_chunks = result.chunks
    except Exception as e:
        raise _pipeline_http_error(e) from e

    return SplitResponse(
        document=result_document.title,
        metadata=result_document.metadata,
        reference_definitions=result_document.reference_definitions,
        chunk_count=len(result_chunks),
        chunks=[ChunkResponse(**asdict(c)) for c in result_chunks],
        trace=trace_payload,
    )


@router.post("/split/file", response_model=SplitResponse)
async def split_file(
    file: UploadFile = File(...),  # noqa: B008
    input_format: Literal[
        "auto",
        "markdown",
        "html",
        "docx",
        "text",
        "log",
        "csv",
        "tsv",
        "json",
        "jsonl",
        "xml",
        "yaml",
        "xlsx",
        "toml",
        "sqlite",
        "sql",
        "python",
        "javascript",
        "typescript",
        "notebook",
    ] = Form("auto"),
    max_tokens: int = Form(1200, gt=0),
    ideal_max_tokens_ratio: float = Form(0.8, gt=0, le=1),
    merge_below_ratio: float = Form(0.125, ge=0, lt=1),
    skip_empty_sections: bool = Form(True),
    heading_sensitive: bool = Form(True),
    block_configs: str = Form(""),
    tokenizer: TokenizerName = Form(  # noqa: B008
        "approx", description="Tokenizer engine used only to encode and count text."
    ),
    splitter: SplitterName = Form(  # noqa: B008
        "section",
        description=(
            "Splitter topology and counting mode. Unprefixed names use "
            "incremental measurement; exact-* names fully recount candidates."
        ),
    ),
    max_heading_level: int | None = Form(None, ge=0),
    trace_stages: list[TraceStage] = Form([]),  # noqa: B008
    trace_max_bytes: int = Form(1_048_576, gt=0, le=10_485_760),
) -> SplitResponse:
    """Split an uploaded supported document file into chunks.

    The input format is auto-detected from the file extension when
    ``input_format`` is ``"auto"``. Set an explicit format to override.
    """
    raw = await file.read()
    fmt = (
        input_format
        if input_format != "auto"
        else detect_format_from_filename(file.filename or "")
    )

    block_options = _parse_form_block_configs(block_configs)

    try:
        if fmt in {"docx", "sqlite", "xlsx"}:
            content = raw
        else:
            content = raw.decode("utf-8")
        tokenizer_instance = _TOKENIZERS.create(tokenizer)
        trace_payload: dict[str, object] | None = None
        if trace_stages:
            trace = trace_source(
                content,
                format=cast(InputFormat, fmt),
                document_title=file.filename,
                source_path=file.filename,
                max_tokens=max_tokens,
                ideal_max_tokens_ratio=ideal_max_tokens_ratio,
                merge_below_ratio=merge_below_ratio,
                skip_empty_sections=skip_empty_sections,
                heading_sensitive=heading_sensitive,
                block_options=block_options,
                tokenizer=tokenizer_instance,
                splitter=splitter,
                max_heading_level=max_heading_level,
            )
            result_document = trace.document
            result_chunks = trace.chunks
            trace_payload = select_trace_stages(
                trace,
                trace_stages,
                max_bytes=trace_max_bytes,
            )
        else:
            result = split_source(
                content,
                format=cast(InputFormat, fmt),
                document_title=file.filename,
                source_path=file.filename,
                max_tokens=max_tokens,
                ideal_max_tokens_ratio=ideal_max_tokens_ratio,
                merge_below_ratio=merge_below_ratio,
                skip_empty_sections=skip_empty_sections,
                heading_sensitive=heading_sensitive,
                block_options=block_options,
                tokenizer=tokenizer_instance,
                splitter=splitter,
                max_heading_level=max_heading_level,
            )
            result_document = result.document
            result_chunks = result.chunks
    except Exception as e:
        raise _pipeline_http_error(e) from e

    return SplitResponse(
        document=result_document.title,
        metadata=result_document.metadata,
        reference_definitions=result_document.reference_definitions,
        chunk_count=len(result_chunks),
        chunks=[ChunkResponse(**asdict(c)) for c in result_chunks],
        trace=trace_payload,
    )
