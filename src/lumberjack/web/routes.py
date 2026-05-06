from __future__ import annotations

from dataclasses import asdict

from fastapi import APIRouter, File, Form, UploadFile

from lumberjack.api import _parse_markdown, lumber
from lumberjack.core import create_tokenizer
from lumberjack.models import SplitOptions

from .pipeline import WebParser, WebSplitter

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
    document_title: str,
) -> tuple[str, str] | None:
    """Resolve text/file input into (content, title), or None if both are missing."""
    if file is not None:
        content = (await file.read()).decode("utf-8")
        return content, file.filename or document_title
    if text is not None:
        return text, document_title
    return None


def _parse_block_types(raw: str) -> frozenset[str]:
    """Parse a comma-separated block-type string into a validated frozenset."""
    return frozenset(b.strip() for b in raw.split(",") if b.strip() in _VALID_SPLIT_BLOCKS)


@router.post("/split")
async def split(
    text: str | None = Form(None),
    file: UploadFile | None = _file_default,
    max_tokens: int = Form(1200),
    merge_below_tokens: int = Form(50),
    overlap_tokens: int = Form(0),
    retain_headings: bool = Form(True),
    include_common_headings: bool = Form(True),
    merge_small_chunks: bool = Form(True),
    isolate_front_matter: bool = Form(True),
    split_oversized_blocks: str = Form("paragraph,blockquote,html_block"),
    tokenizer: str = Form("simple"),
    document_title: str = Form("document.md"),
) -> dict:
    """Split Markdown text or an uploaded file into chunks and return JSON results."""
    resolved = await _resolve_input(text, file, document_title)
    if resolved is None:
        return {"error": "Provide either markdown text or upload a file"}
    content, title = resolved

    blocks = _parse_block_types(split_oversized_blocks)

    chunks = lumber(
        content,
        document_title=title,
        max_tokens=max_tokens,
        merge_below_tokens=merge_below_tokens,
        overlap_tokens=overlap_tokens,
        retain_headings=retain_headings,
        include_common_headings=include_common_headings,
        merge_small_chunks=merge_small_chunks,
        isolate_front_matter=isolate_front_matter,
        split_oversized_blocks=blocks,
        tokenizer=tokenizer,
    )

    return {
        "document": title,
        "chunk_count": len(chunks),
        "chunks": [asdict(c) for c in chunks],
    }


@router.post("/pipeline")
async def pipeline(
    text: str | None = Form(None),
    file: UploadFile | None = _file_default,
    max_tokens: int = Form(1200),
    merge_below_tokens: int = Form(50),
    overlap_tokens: int = Form(0),
    retain_headings: bool = Form(True),
    include_common_headings: bool = Form(True),
    merge_small_chunks: bool = Form(True),
    isolate_front_matter: bool = Form(True),
    split_oversized_blocks: str = Form("paragraph,blockquote,html_block"),
    tokenizer: str = Form("simple"),
    document_title: str = Form("document.md"),
) -> dict:
    """Return all intermediate pipeline stages for visualization."""
    resolved = await _resolve_input(text, file, document_title)
    if resolved is None:
        return {"error": "Provide either markdown text or upload a file"}
    content, title = resolved

    blocks = _parse_block_types(split_oversized_blocks)

    # Stage 1: Raw text info
    lines = content.splitlines()

    # Stage 2: Parser tokens
    parser_impl = WebParser()
    tokens = parser_impl.parse_tokens(content)

    # Stage 3: Document AST
    document = _parse_markdown(content, document_title=title)

    # Stage 4-5: Splitting with intermediate data
    tokenizer_impl = create_tokenizer(tokenizer)
    splitter = WebSplitter(
        tokenizer=tokenizer_impl,
        options=SplitOptions(
            max_tokens=max_tokens,
            merge_below_tokens=merge_below_tokens,
            overlap_tokens=overlap_tokens,
            retain_headings=retain_headings,
            include_common_headings=include_common_headings,
            merge_small_chunks=merge_small_chunks,
            isolate_front_matter=isolate_front_matter,
            split_oversized_blocks=blocks,
        ),
    )
    steps = splitter.split_with_steps(document)

    return {
        "stage_1_raw": {
            "char_count": len(content),
            "line_count": len(lines),
            "word_count": len(content.split()),
            "full_text": content,
        },
        "stage_2_tokens": {
            "count": len(tokens),
            "tokens": tokens,
        },
        "stage_3_ast": {
            "document_title": document.title,
            "root": asdict(document.root),
            "reference_definitions": document.reference_definitions,
        },
        "stage_4_split": {
            "entries": [asdict(e) for e in steps.entries],
            "drafts": [asdict(d) for d in steps.drafts_after_merge],
            "options": {
                "max_tokens": max_tokens,
                "merge_below_tokens": merge_below_tokens,
                "overlap_tokens": overlap_tokens,
            },
        },
        "stage_5_chunks": {
            "document": title,
            "chunk_count": len(steps.chunks),
            "chunks": [asdict(c) for c in steps.chunks],
        },
    }
