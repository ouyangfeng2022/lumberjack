"""Versioned JSON serialization for Lumberjack's public result models."""

from __future__ import annotations

from dataclasses import fields, is_dataclass
from pathlib import Path
from typing import Any

from .models import (
    Chunk,
    DocTree,
    DocumentBlock,
    DocumentInline,
    SectionNode,
    SourceLocation,
    SplitResult,
)

CHUNK_SCHEMA_VERSION = "lumberjack.chunk.v1"
DOC_TREE_SCHEMA_VERSION = "lumberjack.doc-tree.v1"


def _json_value(value: object) -> Any:
    if isinstance(value, Path):
        return str(value)
    if is_dataclass(value) and not isinstance(value, type):
        return {
            field.name: _json_value(getattr(value, field.name))
            for field in fields(value)
        }
    if isinstance(value, dict):
        return {str(key): _json_value(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [_json_value(item) for item in value]
    return value


def chunk_to_dict(chunk: Chunk) -> dict[str, Any]:
    """Serialize a final chunk using the stable v1 JSON representation."""
    value = _json_value(chunk)
    assert isinstance(value, dict)
    return value


def chunk_from_dict(payload: dict[str, Any]) -> Chunk:
    """Deserialize a v1 chunk payload, restoring tuple-valued model fields."""
    locations = tuple(SourceLocation(**item) for item in payload["source_locations"])
    own_heading = payload["own_heading"]
    return Chunk(
        chunk_id=str(payload["chunk_id"]),
        chunk_type=str(payload["chunk_type"]),
        body=str(payload["body"]),
        token_count=int(payload["token_count"]),
        estimated_token_count=int(payload["estimated_token_count"]),
        headings_token_count=int(payload["headings_token_count"]),
        body_token_count=int(payload["body_token_count"]),
        ancestor_headings=tuple(
            (int(item[0]), str(item[1])) for item in payload["ancestor_headings"]
        ),
        own_heading=(int(own_heading[0]), str(own_heading[1]))
        if own_heading is not None
        else None,
        section_level=int(payload["section_level"]),
        document_title=str(payload["document_title"]),
        document_path=payload["document_path"],
        start_line=payload["start_line"],
        end_line=payload["end_line"],
        source_locations=locations,
        protected=bool(payload["protected"]),
    )


def split_result_to_dict(result: SplitResult) -> dict[str, Any]:
    """Serialize the stable CLI/Web/integration result envelope."""
    return {
        "schema_version": CHUNK_SCHEMA_VERSION,
        "document": result.document.title,
        "metadata": _json_value(result.document.metadata),
        "reference_definitions": _json_value(result.document.reference_definitions),
        "chunk_count": len(result.chunks),
        "chunks": [chunk_to_dict(chunk) for chunk in result.chunks],
    }


def split_result_from_dict(payload: dict[str, Any], document: DocTree) -> SplitResult:
    """Deserialize a result envelope; callers supply its separately parsed DocTree."""
    if payload.get("schema_version") != CHUNK_SCHEMA_VERSION:
        raise ValueError("unsupported chunk schema version")
    return SplitResult(
        document=document, chunks=[chunk_from_dict(item) for item in payload["chunks"]]
    )


def doc_tree_to_dict(tree: DocTree) -> dict[str, Any]:
    """Serialize a parsed tree for persistence or adapter boundaries."""
    return {"schema_version": DOC_TREE_SCHEMA_VERSION, **_json_value(tree)}


def _inline_from_dict(value: dict[str, Any]) -> DocumentInline:
    return DocumentInline(
        kind=value["kind"],
        text=value.get("text", ""),
        children=tuple(_inline_from_dict(item) for item in value.get("children", [])),
        attrs=value.get("attrs", {}),
    )


def _block_from_dict(value: dict[str, Any]) -> DocumentBlock:
    return DocumentBlock(
        kind=value["kind"],
        text=value["text"],
        start_line=value.get("start_line"),
        end_line=value.get("end_line"),
        source_locations=tuple(
            SourceLocation(**item) for item in value.get("source_locations", [])
        ),
        children=tuple(_block_from_dict(item) for item in value.get("children", [])),
        inlines=tuple(_inline_from_dict(item) for item in value.get("inlines", [])),
        attrs=value.get("attrs", {}),
    )


def _section_from_dict(value: dict[str, Any]) -> SectionNode:
    return SectionNode(
        level=value["level"],
        title=value["title"],
        path=tuple(tuple(item) for item in value.get("path", [])),
        index=value.get("index", 0),
        start_line=value.get("start_line"),
        source_locations=tuple(
            SourceLocation(**item) for item in value.get("source_locations", [])
        ),
        title_inlines=tuple(
            _inline_from_dict(item) for item in value.get("title_inlines", [])
        ),
        blocks=[_block_from_dict(item) for item in value.get("blocks", [])],
        children=[_section_from_dict(item) for item in value.get("children", [])],
    )


def doc_tree_from_dict(payload: dict[str, Any]) -> DocTree:
    """Deserialize a complete v1 document-tree representation."""
    if payload.get("schema_version") != DOC_TREE_SCHEMA_VERSION:
        raise ValueError("unsupported DocTree schema version")
    return DocTree(
        title=payload["title"],
        source=payload["source"],
        root=_section_from_dict(payload["root"]),
        source_path=payload.get("source_path"),
        metadata=payload.get("metadata", {}),
        reference_definitions=payload.get("reference_definitions", {}),
        topology=payload.get("topology", "hierarchical"),
    )


__all__ = [
    "CHUNK_SCHEMA_VERSION",
    "DOC_TREE_SCHEMA_VERSION",
    "chunk_from_dict",
    "chunk_to_dict",
    "doc_tree_from_dict",
    "doc_tree_to_dict",
    "split_result_from_dict",
    "split_result_to_dict",
]
