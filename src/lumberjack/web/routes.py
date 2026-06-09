from __future__ import annotations

import json
from dataclasses import asdict
from typing import Annotated, Any

from fastapi import APIRouter, Body, Depends, File, Form, HTTPException, UploadFile
from pydantic import BaseModel, ConfigDict

from lumberjack import lumber
from lumberjack.core.models import BlockConfig

router = APIRouter()


class SplitRequestOptions(BaseModel):
    model_config = ConfigDict(extra="ignore")

    max_tokens: int = 1200
    ideal_max_tokens_ratio: float = 0.8
    merge_below_tokens: int = 50
    overlap_tokens: int = 0
    merge_small_chunks: bool = True
    skip_empty_sections: bool = True
    recursive_split: bool = False
    block_configs: dict[str, Any] | None = None
    disable_lheading: bool = False
    tokenizer: str = "simple"
    splitter: str = "recursive"


class TextSplitRequest(SplitRequestOptions):
    text: str


_BLOCK_CONFIG_FIELDS = frozenset({"isolated", "split", "max_tokens"})


def _validate_block_configs(
    block_configs: dict[str, Any] | None,
) -> dict[str, BlockConfig] | None:
    if block_configs is None:
        return None

    resolved: dict[str, BlockConfig] = {}
    for kind, config in block_configs.items():
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


def _split_markdown(
    content: str,
    *,
    document_title: str | None,
    options: SplitRequestOptions,
) -> dict:
    block_options = _validate_block_configs(options.block_configs)

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
            recursive_split=options.recursive_split,
            block_options=block_options,
            disable_lheading=options.disable_lheading,
            tokenizer=options.tokenizer,
            splitter=options.splitter,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e

    return {
        "document": chunks[0].document_title if chunks else "Anonymous",
        "chunk_count": len(chunks),
        "chunks": [asdict(c) for c in chunks],
    }


def _parse_form_block_configs(block_configs: str) -> dict[str, Any] | None:
    if not block_configs or not block_configs.strip():
        return None
    try:
        return json.loads(block_configs)
    except json.JSONDecodeError as e:
        raise HTTPException(status_code=400, detail="Invalid block_configs JSON") from e


def _form_options(
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
) -> SplitRequestOptions:
    return SplitRequestOptions(
        max_tokens=max_tokens,
        ideal_max_tokens_ratio=ideal_max_tokens_ratio,
        merge_below_tokens=merge_below_tokens,
        overlap_tokens=overlap_tokens,
        merge_small_chunks=merge_small_chunks,
        skip_empty_sections=skip_empty_sections,
        recursive_split=recursive_split,
        block_configs=_parse_form_block_configs(block_configs),
        disable_lheading=disable_lheading,
        tokenizer=tokenizer,
        splitter=splitter,
    )


@router.post("/split/text")
async def split_text(payload: Annotated[TextSplitRequest, Body()]) -> dict:
    """Split Markdown text from a JSON request body into chunks."""
    return _split_markdown(payload.text, document_title=None, options=payload)


@router.post("/split/file")
async def split_file(
    file: Annotated[UploadFile, File()],
    options: Annotated[SplitRequestOptions, Depends(_form_options)],
) -> dict:
    """Split an uploaded Markdown file into chunks."""
    content = (await file.read()).decode("utf-8")
    return _split_markdown(content, document_title=file.filename, options=options)
