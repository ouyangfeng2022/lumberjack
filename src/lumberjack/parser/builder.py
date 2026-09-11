"""Supported construction API for parsers that target :class:`DocTree`."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import Any, Literal

from ..block import BlockKind
from ..models import (
    DocTree,
    DocumentBlock,
    DocumentInline,
    SectionNode,
    SourceLocation,
)


class DocTreeBuilder:
    """Incrementally construct a validated, format-neutral document tree.

    The builder deliberately permits blocks directly on the root.  Parsers for
    flat records (CSV, JSONL, logs) must use that form instead of inventing a
    heading hierarchy solely to satisfy a section-oriented API.
    """

    def __init__(
        self,
        *,
        title: str = "Anonymous",
        source: str = "",
        source_path: str | Path | None = None,
        metadata: Mapping[str, Any] | None = None,
        reference_definitions: Mapping[str, Mapping[str, str]] | None = None,
        block_kinds: Iterable[str | BlockKind] | None = None,
        topology: Literal["hierarchical", "records"] = "hierarchical",
    ) -> None:
        normalized_title = title.strip() or "Anonymous"
        self._root = SectionNode(level=0, title=normalized_title)
        self._stack: list[SectionNode] = [self._root]
        self._title = normalized_title
        self._source = source
        self._source_path = str(source_path) if source_path is not None else None
        self._metadata = dict(metadata or {})
        self._reference_definitions = {
            str(label): dict(definition)
            for label, definition in (reference_definitions or {}).items()
        }
        self._block_kinds = {
            str(kind).strip().lower()
            for kind in (block_kinds or BlockKind)
            if str(kind).strip()
        }
        if topology not in {"hierarchical", "records"}:
            raise ValueError(f"unsupported document topology: {topology!r}")
        self._topology = topology

    @property
    def current_section(self) -> SectionNode:
        """The section receiving subsequent blocks."""
        return self._stack[-1]

    def add_section(
        self,
        level: int,
        title: str,
        *,
        location: SourceLocation | None = None,
        inlines: Iterable[DocumentInline] = (),
    ) -> DocTreeBuilder:
        """Add a heading section and select it as the current section."""
        if self._topology == "records":
            raise ValueError("record documents cannot contain heading sections")
        if not isinstance(level, int) or isinstance(level, bool) or not 1 <= level <= 6:
            raise ValueError("section level must be an integer from 1 through 6")
        normalized_title = title.strip()
        if not normalized_title:
            raise ValueError("section title cannot be empty")

        while self._stack[-1].level >= level:
            self._stack.pop()
        parent = self._stack[-1]
        section = SectionNode(
            level=level,
            title=normalized_title,
            path=(*parent.path, (level, normalized_title)),
            index=len(parent.children),
            start_line=location.line_start if location is not None else None,
            source_locations=(location,) if location is not None else (),
            title_inlines=tuple(inlines),
        )
        parent.add_child(section)
        self._stack.append(section)
        return self

    def declare_block_kind(self, kind: str | BlockKind) -> DocTreeBuilder:
        """Declare an extension block kind before emitting it."""
        normalized_kind = str(kind).strip().lower()
        if not normalized_kind:
            raise ValueError("block kind cannot be empty")
        self._block_kinds.add(normalized_kind)
        return self

    def add_block(
        self,
        kind: str | BlockKind,
        text: str,
        *,
        locations: Iterable[SourceLocation] = (),
        children: Iterable[DocumentBlock] = (),
        inlines: Iterable[DocumentInline] = (),
        attrs: Mapping[str, Any] | None = None,
    ) -> DocTreeBuilder:
        """Add one canonical rendered block to the current section."""
        normalized_kind = str(kind).strip().lower()
        if not normalized_kind:
            raise ValueError("block kind cannot be empty")
        if normalized_kind not in self._block_kinds:
            raise ValueError(f"undeclared block kind: {normalized_kind!r}")
        block_locations = tuple(locations)
        start_line = min(
            (
                location.line_start
                for location in block_locations
                if location.line_start
            ),
            default=None,
        )
        end_line = max(
            (location.line_end for location in block_locations if location.line_end),
            default=None,
        )
        self.current_section.add_block(
            DocumentBlock(
                kind=normalized_kind,
                text=text,
                start_line=start_line,
                end_line=end_line,
                source_locations=block_locations,
                children=tuple(children),
                inlines=tuple(inlines),
                attrs=dict(attrs or {}),
            )
        )
        return self

    def add_record(
        self,
        text: str,
        *,
        kind: str = "record",
        locations: Iterable[SourceLocation],
        attrs: Mapping[str, Any] | None = None,
    ) -> DocTreeBuilder:
        """Add one ordered, atomic record with explicit record provenance."""
        if self._topology != "records":
            raise ValueError("add_record requires topology='records'")
        record_locations = tuple(locations)
        if not record_locations:
            raise ValueError("record locations cannot be empty")
        if not all(
            location.row_start is not None
            or location.json_path is not None
            or location.element_id is not None
            for location in record_locations
        ):
            raise ValueError(
                "record locations must include row, json_path, or element_id provenance"
            )
        return self.add_block(
            kind,
            text,
            locations=record_locations,
            attrs={**dict(attrs or {}), "record": True},
        )

    def add_field_value(
        self,
        field: str,
        value: object,
        *,
        locations: Iterable[SourceLocation] = (),
        attrs: Mapping[str, Any] | None = None,
    ) -> DocTreeBuilder:
        """Add one scalar field/value unit without turning its key into a heading."""
        normalized_field = field.strip()
        if not normalized_field:
            raise ValueError("field name cannot be empty")
        return self.add_block(
            "field_value",
            f"{normalized_field}: {value}",
            locations=locations,
            attrs={**dict(attrs or {}), "field": normalized_field, "value": value},
        )

    def build(self) -> DocTree:
        """Return the completed tree after validating every section path."""
        self._validate_section(self._root, parent_path=())
        return DocTree(
            title=self._title,
            source=self._source,
            root=self._root,
            source_path=self._source_path,
            metadata=dict(self._metadata),
            reference_definitions=dict(self._reference_definitions),
            topology=self._topology,
        )

    def _validate_section(
        self,
        section: SectionNode,
        *,
        parent_path: tuple[tuple[int, str], ...],
    ) -> None:
        if section.level == 0:
            if section.path:
                raise ValueError("root section path must be empty")
        elif section.path != (*parent_path, section.heading_key):
            raise ValueError("section path does not match its parent hierarchy")
        for index, child in enumerate(section.children):
            if child.index != index:
                raise ValueError("section sibling indexes must be contiguous")
            if child.level <= section.level:
                raise ValueError("child section level must exceed its parent level")
            self._validate_section(child, parent_path=section.path)


__all__ = ["DocTreeBuilder"]
