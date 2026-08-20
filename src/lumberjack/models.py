from __future__ import annotations

from base64 import b64encode
from collections.abc import Iterable
from dataclasses import dataclass, field, fields, is_dataclass
from pathlib import Path
from typing import Any, Literal, TypeAlias, cast

from lumberjack.block import BlockKind

from ._internal.rendering import join_rendered_blocks

HeadingKey: TypeAlias = tuple[int, str]
HeadingPath: TypeAlias = tuple[HeadingKey, ...]
InputFormat: TypeAlias = Literal[
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
    "bash",
    "c",
    "cpp",
    "csharp",
    "go",
    "java",
    "kotlin",
    "lua",
    "php",
    "ruby",
    "rust",
    "swift",
    "zig",
    "notebook",
]
DocumentTopology: TypeAlias = Literal["hierarchical", "records"]
BoundingBox: TypeAlias = tuple[float, float, float, float]


@dataclass(slots=True, frozen=True)
class SourceLocation:
    """A format-neutral, explicitly partial location in an input document.

    A parser sets only the coordinates it can establish faithfully.  For
    example, Markdown normally provides line ranges, spreadsheet parsers can
    provide sheet/row/column coordinates, and visual parsers can additionally
    provide page and bounding-box coordinates.  ``None`` means unavailable;
    it never means an inferred coordinate.
    """

    source: str | None = None
    byte_start: int | None = None
    byte_end: int | None = None
    line_start: int | None = None
    line_end: int | None = None
    page_start: int | None = None
    page_end: int | None = None
    sheet: str | None = None
    row_start: int | None = None
    row_end: int | None = None
    column_start: int | None = None
    column_end: int | None = None
    json_path: str | None = None
    element_id: str | None = None
    bounding_box: BoundingBox | None = None

    def __post_init__(self) -> None:
        for start_name, end_name in (
            ("byte_start", "byte_end"),
            ("line_start", "line_end"),
            ("page_start", "page_end"),
            ("row_start", "row_end"),
            ("column_start", "column_end"),
        ):
            start = getattr(self, start_name)
            end = getattr(self, end_name)
            if (start is None) != (end is None):
                raise ValueError(f"{start_name} and {end_name} must be set together")
            if start is not None and end is not None and start > end:
                raise ValueError(f"{start_name} must not exceed {end_name}")
        if self.bounding_box is not None and len(self.bounding_box) != 4:
            raise ValueError("bounding_box must contain exactly four coordinates")


@dataclass(slots=True, frozen=True)
class ExtractionResult:
    """Observable output and diagnostics from an external extraction stage."""

    parser_name: str
    parser_version: str | None = None
    raw_output: str | None = None
    normalized_output: str | None = None
    locations: tuple[SourceLocation, ...] = ()
    warnings: tuple[str, ...] = ()
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True, frozen=True)
class PipelineDiagnostic:
    """One non-fatal, user-visible diagnostic emitted by a pipeline stage."""

    stage: str
    message: str
    location: SourceLocation | None = None


@dataclass(slots=True, frozen=True)
class Document:
    """Raw document and provenance waiting to be parsed into a structured document."""

    source: str | bytes | Path
    format: InputFormat = "auto"
    document_title: str | None = None
    metadata_overrides: dict[str, object] = field(default_factory=dict)
    source_path: str | Path | None = None


@dataclass(slots=True, frozen=True)
class DocumentInline:
    """Format-neutral inline node normalized by an input parser.

    Attributes:
        kind: Inline node type (e.g. ``"text"``, ``"link"``, ``"code_inline"``,
            ``"strong"``, ``"em"``, ``"image"``).
        text: Rendered plain text of this node.
        children: Nested inline children (e.g. emphasis wrapping text).
        attrs: Additional attributes (``"href"``, ``"src"``, ``"title"``, etc.).
    """

    kind: str
    text: str = ""
    children: tuple[DocumentInline, ...] = ()
    attrs: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True, frozen=True)
class DocumentBlock:
    """Format-neutral block node in the canonical rendered representation.

    Attributes:
        kind: Block type (e.g. ``"paragraph"``, ``"heading"``, ``"code_fence"``,
            ``"blockquote"``, ``"list"``, ``"list_item"``, ``"table"``,
            ``"html_block"``, ``"math_block"``).
        text: Canonical rendered text consumed by splitters. Markdown input is
            normalized Markdown; HTML and DOCX input is converted to the same
            Markdown-like representation. It is not guaranteed to be a source
            slice.
        start_line: 1-based line number where the block begins.
        end_line: 1-based line number where the block ends.
        children: Nested child blocks for container types (``"blockquote"``,
            ``"list"``, ``"list_item"``).  Empty for leaf blocks.
        inlines: Normalized inline nodes parsed from the block content.
            Populated for ``"paragraph"`` and ``"heading"`` blocks.
        attrs: Additional attributes (e.g. heading level, list style, code language).
    """

    kind: BlockKind | str
    text: str
    start_line: int | None = None
    end_line: int | None = None
    source_locations: tuple[SourceLocation, ...] = ()
    children: tuple[DocumentBlock, ...] = ()
    inlines: tuple[DocumentInline, ...] = ()
    attrs: dict[str, Any] = field(default_factory=dict)


def source_locations_for_blocks(
    blocks: Iterable[DocumentBlock],
) -> tuple[SourceLocation, ...]:
    """Collect parser-defined locations from blocks without changing their order."""
    return tuple(
        dict.fromkeys(
            location for block in blocks for location in block.source_locations
        )
    )


@dataclass(slots=True)
class SectionNode:
    """Heading-tree node representing a section and its children.

    Attributes:
        level: Heading level.
        title: Plain-text heading title.
        path: Tuple of ``(level, title)`` pairs from root to this section.
        blocks: Block-level content directly under this section (not in sub-sections).
        children: Child sections (sub-headings nested within this section).
        index: Position of this section among its siblings (0-based).
        start_line: 1-based line number where the section heading begins.
        title_inlines: Normalized inline nodes parsed from the heading text.
    """

    level: int
    title: str
    path: HeadingPath = ()
    blocks: list[DocumentBlock] = field(default_factory=list)
    children: list[SectionNode] = field(default_factory=list)
    index: int = 0
    start_line: int | None = None
    source_locations: tuple[SourceLocation, ...] = ()
    title_inlines: tuple[DocumentInline, ...] = ()

    @property
    def heading_key(self) -> HeadingKey:
        return (self.level, self.title)

    def add_block(self, block: DocumentBlock) -> None:
        """Append a block (roughly one paragraph) to this section."""
        self.blocks.append(block)

    def add_child(self, child: SectionNode) -> None:
        self.children.append(child)


@dataclass(slots=True, frozen=True)
class DocTree:
    """Parsed document with a normalized section tree, source, and metadata.

    Attributes:
        title: Document title.  Priority: user-provided ``document_title``,
            then front matter ``title`` field, then first level-1 heading,
            then ``"Anonymous"``.
        source: Original text for Markdown and HTML inputs. Binary parsers may
            leave this empty or provide a normalized textual representation.
        root: Root section node of the heading tree.
        source_path: Original file path or caller-supplied source provenance.
        metadata: Semantic document metadata parsed from the source and merged
            with caller-provided overrides.
        reference_definitions: Link/image reference definitions (``[label]: url``).
        topology: Structural semantics of the root. ``"records"`` is a flat,
            ordered sequence of atomic records rather than a heading tree.
    """

    title: str
    source: str
    root: SectionNode
    source_path: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    reference_definitions: dict[str, dict[str, str]] = field(default_factory=dict)
    topology: DocumentTopology = "hierarchical"

    def __post_init__(self) -> None:
        if self.topology not in {"hierarchical", "records"}:
            raise ValueError(f"unsupported document topology: {self.topology!r}")
        if self.topology == "records" and self.root.children:
            raise ValueError("record documents cannot contain heading sections")


@dataclass(slots=True, frozen=True)
class Chunk:
    """Final chunk payload with separated heading/body content and token counts.

    Attributes:
        chunk_id: Unique identifier for this chunk.
        chunk_type: Origin block type (e.g. ``"paragraph"``, ``"heading"``,
            ``"code_fence"``, ``"document"``).
        body: Rendered chunk body. Ancestor and own headings are never rendered
            here; headings needed to represent merged internal sections remain.
        token_count: Sum of heading tokens, ``tokenizer.count("\n\n")``, and
            body tokens.
        estimated_token_count: Split-time running estimate (additive + separator-delta
            window). ``token_count`` is the authoritative final total. The two
            may differ slightly for incremental splitters due to join approximations.
        headings_token_count: Token count of the canonical Markdown rendering of
            the complete heading path.
        body_token_count: Token count of ``body``.
        ancestor_headings: Tuple of ``(level, title)`` pairs representing the
            chunk's ancestor heading path.
        own_heading: The chunk's own ``(level, title)`` heading, or ``None``
            when the chunk represents multiple merged sibling sections.

        section_level: Deepest heading level in this chunk.

            ``section_level`` is derived from the full section paths covered by
            the chunk, not from the ancestor-only ``ancestor_headings`` metadata.

        document_title: Title of the source document.
        document_path: File path of the source document, if split from a file.
        start_line: 1-based line number where this chunk begins in the source.
        end_line: 1-based line number where this chunk ends in the source.
    """

    chunk_id: str
    chunk_type: str = "paragraph"
    body: str = ""
    token_count: int = 0
    estimated_token_count: int = 0
    headings_token_count: int = 0
    body_token_count: int = 0
    ancestor_headings: HeadingPath = ()
    own_heading: HeadingKey | None = None
    section_level: int = 0
    document_title: str = ""
    document_path: str | None = None
    start_line: int | None = None
    end_line: int | None = None
    source_locations: tuple[SourceLocation, ...] = ()
    protected: bool = False


@dataclass(slots=True, frozen=True)
class SplitResult:
    """Document-level result of one complete splitting pipeline run."""

    document: DocTree
    chunks: list[Chunk]


@dataclass(slots=True, frozen=True)
class PipelineTrace:
    """Explicit, complete record of one document's parsing and split stages.

    ``Lumberjack.saw()`` intentionally returns :class:`SplitResult`; callers
    that need intermediate representations opt into this object via
    :meth:`Lumberjack.trace`.
    """

    input: Document
    extraction: ExtractionResult | None
    document: DocTree
    drafts: tuple[ChunkDraft, ...]
    chunks: tuple[Chunk, ...]
    diagnostics: tuple[PipelineDiagnostic, ...] = ()

    def to_dict(self) -> dict[str, object]:
        """Return a JSON-compatible view of this trace.

        Bytes are represented explicitly as a base64 envelope and paths as
        strings.  The versioned JSON Schema for persisted trace payloads is a
        later concern; this method keeps the public Python trace inspectable
        without exposing private implementation objects.
        """
        value = _json_value(self)
        assert isinstance(value, dict)
        return cast(dict[str, object], value)


def _json_value(value: object) -> object:
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, bytes):
        return {"encoding": "base64", "data": b64encode(value).decode("ascii")}
    if is_dataclass(value) and not isinstance(value, type):
        return {
            item.name: _json_value(getattr(value, item.name)) for item in fields(value)
        }
    if isinstance(value, dict):
        return {str(key): _json_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_value(item) for item in value]
    return value


def render_heading_path(path: HeadingPath) -> str:
    """Render a full heading breadcrumb path as nested Markdown headings."""

    def _render_heading(level: int, title: str) -> str:
        """Render a heading as a Markdown ATX heading string."""
        if level <= 0:
            return title.strip()
        return f"{'#' * level} {title.strip()}"

    return join_rendered_blocks(
        [_render_heading(level, title) for level, title in path]
    )


def complete_heading_path(
    ancestor_headings: HeadingPath,
    own_heading: HeadingKey | None,
) -> HeadingPath:
    """Return the complete external path for a chunk's separated headings."""
    if own_heading is None:
        return ancestor_headings
    return (*ancestor_headings, own_heading)


def common_heading_path(paths: Iterable[HeadingPath]) -> HeadingPath:
    iterator = iter(paths)
    first = tuple(next(iterator, ()))
    common = first
    for path in iterator:
        limit = min(len(common), len(path))
        index = 0
        while index < limit and common[index] == path[index]:
            index += 1
        common = common[:index]
        if not common:
            break
    return common


def ancestor_heading_path(paths: Iterable[HeadingPath]) -> HeadingPath:
    path_list = [tuple(path) for path in paths]
    if not path_list:
        return ()

    first = path_list[0]
    if all(path == first for path in path_list):
        return first[:-1] if first else ()

    return common_heading_path(path_list)


@dataclass(slots=True)
class Entry:
    """Rendered content unit with heading context and line range, a flattened SectionNode.

    Args:
        headings: Full heading path for the entry, used for rendering and metadata.
        body: Rendered Markdown body text for the entry, excluding headings.
        start_line: Starting line number of the entry in the original document, if available.
        end_line: Ending line number of the entry in the original document, if available.
        body_token_count: Cached token count for the entry body, excluding headings.
    """

    headings: HeadingPath
    body: str
    start_line: int | None
    end_line: int | None
    body_token_count: int = 0
    source_locations: tuple[SourceLocation, ...] = ()


def render_draft_body(entries: list[Entry], external_headings: HeadingPath) -> str:
    """Render draft entries while keeping external headings as metadata."""
    parts: list[str] = []
    previous_headings = external_headings
    for entry in entries:
        shared = common_heading_path((previous_headings, entry.headings))
        if len(shared) < len(external_headings):
            shared = external_headings
        relative_headings = entry.headings[len(shared) :]
        entry_parts: list[str] = []
        if relative_headings:
            entry_parts.append(render_heading_path(relative_headings))
        if entry.body:
            entry_parts.append(entry.body)
        rendered = join_rendered_blocks(entry_parts)
        if rendered:
            parts.append(rendered)
        previous_headings = entry.headings
    return join_rendered_blocks(parts)


@dataclass(slots=True)
class ChunkDraft:
    """Intermediate split result holding grouped entries and a token estimate.

    Args:
        entries: List of entries to be merged into the chunk, with heading context and body.
        headings: Full external heading path excluded from the rendered body.
        own_heading: Optional final heading identifying the chunk itself.

            ``# H1 \n\n ## H2.1 \n\n Content1``, headings=[(1, "H1"), (2, "H2.1")].

            ``# H1 \n\n ## H2.1 \n\n Content1 ## H2.2 \n\n Content2``, headings=[(1, "H1")].

        headings_token_count: The token count for the chunk's full heading path.
        body_token_count: The token count for the chunk body (sum of entry body_token_count plus separator deltas).
        token_count: Split-time sum of heading tokens, the external-heading
            separator, and body tokens.
        split_origin: The split operation that produced this draft, for debugging/analysis.
        chunk_type: The draft content type (e.g. "paragraph", "code_block"), used for metadata.

    """

    entries: list[Entry]
    headings: HeadingPath
    own_heading: HeadingKey | None
    headings_token_count: int
    body_token_count: int
    token_count: int
    split_origin: Literal["section", "fragment", "text_piece", "merge"] = "section"
    chunk_type: str = "paragraph"
    counting_mode: Literal["incremental", "exact"] = "incremental"
    protected: bool = False
