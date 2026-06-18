from __future__ import annotations

from typing import TYPE_CHECKING

from lumberjack.core.markdown.parser import MarkdownParser
from lumberjack.core.visitor import MarkdownAstVisitor

if TYPE_CHECKING:
    from lumberjack.core.models import (
        DocumentAST,
        MarkdownBlock,
        MarkdownInline,
        SectionNode,
    )

# -- Fixtures -----------------------------------------------------------------

FLAT_FIXTURE = """# Title

Paragraph one.

Paragraph two.
"""

NESTED_FIXTURE = """# Document

Intro paragraph with **bold** and *italic*.

## Section A

> Quote paragraph.
>
> 1. ordered item

- item one
- item two

### Sub A

```python
print("hello")
```

## Section B

End.
"""


# -- Helpers ------------------------------------------------------------------


class EventRecorder(MarkdownAstVisitor):
    """Records (event_type, kind_or_title, level_or_none) for every hook call."""

    def __init__(self) -> None:
        self.events: list[tuple[str, str, int | None]] = []

    def visit_section(self, section: SectionNode) -> None:
        self.events.append(("enter_section", section.title, section.level))

    def depart_section(self, section: SectionNode) -> None:
        self.events.append(("depart_section", section.title, section.level))

    def visit_block(self, block: MarkdownBlock) -> None:
        self.events.append(("enter_block", block.kind, None))

    def depart_block(self, block: MarkdownBlock) -> None:
        self.events.append(("depart_block", block.kind, None))

    def visit_inline(self, inline: MarkdownInline) -> None:
        self.events.append(("enter_inline", inline.kind, None))

    def depart_inline(self, inline: MarkdownInline) -> None:
        self.events.append(("depart_inline", inline.kind, None))


# -- Tests --------------------------------------------------------------------


def test_visitor_traverses_flat_document() -> None:
    """Visitor walks root section, its blocks, then departs."""
    document = MarkdownParser().parse(FLAT_FIXTURE, document_title="flat.md")
    recorder = EventRecorder()
    recorder.walk_document(document)

    # Root section (level 0) → 1 child heading (level 1) with 2 paragraphs
    assert recorder.events == [
        ("enter_section", "flat.md", 0),
        ("enter_section", "Title", 1),
        ("enter_block", "paragraph", None),
        ("enter_inline", "text", None),
        ("depart_inline", "text", None),
        ("depart_block", "paragraph", None),
        ("enter_block", "paragraph", None),
        ("enter_inline", "text", None),
        ("depart_inline", "text", None),
        ("depart_block", "paragraph", None),
        ("depart_section", "Title", 1),
        ("depart_section", "flat.md", 0),
    ]


def test_visitor_traverses_nested_sections() -> None:
    """Visitor walks child sections recursively in document order."""
    document = MarkdownParser().parse(NESTED_FIXTURE, document_title="nested.md")
    recorder = EventRecorder()
    recorder.walk_document(document)

    section_events = [(e, t, lv) for e, t, lv in recorder.events if "section" in e]
    # Root → H1 → H2 "Section A" → H3 "Sub A" → depart Sub A → depart Section A →
    # H2 "Section B" → depart Section B → depart H1 → depart root
    assert section_events == [
        ("enter_section", "nested.md", 0),
        ("enter_section", "Document", 1),
        ("enter_section", "Section A", 2),
        ("enter_section", "Sub A", 3),
        ("depart_section", "Sub A", 3),
        ("depart_section", "Section A", 2),
        ("enter_section", "Section B", 2),
        ("depart_section", "Section B", 2),
        ("depart_section", "Document", 1),
        ("depart_section", "nested.md", 0),
    ]


def test_visitor_traverses_nested_blocks() -> None:
    """Visitor walks block children (blockquote > list > list_item)."""
    document = MarkdownParser().parse(NESTED_FIXTURE, document_title="nested.md")
    recorder = EventRecorder()
    recorder.walk_document(document)

    # Find the blockquote in Section A
    section_a_enter = recorder.events.index(("enter_section", "Section A", 2))
    # Collect block events after Section A enters until its depart
    block_events: list[tuple[str, str, int | None]] = []
    for ev in recorder.events[section_a_enter + 1 :]:
        if ev[0] == "enter_section":
            break
        if ev[0] in ("enter_block", "depart_block"):
            block_events.append(ev)

    # blockquote → paragraph (inside quote) → list (inside quote) →
    # list_item → list_item → list → list_item → list_item
    block_kinds = [kind for _, kind, _ in block_events]
    assert "blockquote" in block_kinds
    assert "list" in block_kinds

    # Verify blockquote is present with nested children, followed by a top-level list
    assert block_events[0] == ("enter_block", "blockquote", None)
    # Last block in Section A is the list (blockquote comes first, then list)
    assert block_events[-1] == ("depart_block", "list", None)


def test_visitor_traverses_inlines() -> None:
    """Visitor walks inline nodes including nested children (strong > text)."""
    document = MarkdownParser().parse(NESTED_FIXTURE, document_title="nested.md")
    recorder = EventRecorder()
    recorder.walk_document(document)

    # The intro paragraph has **bold** and *italic*
    inline_events = [
        (e, t) for e, t, _ in recorder.events if e in ("enter_inline", "depart_inline")
    ]
    # Should contain strong and emphasis
    inline_kinds = {kind for _, kind in inline_events}
    assert "strong" in inline_kinds
    assert "emphasis" in inline_kinds
    assert "text" in inline_kinds


def test_visitor_heading_collector_subclass() -> None:
    """Subclass that collects all heading levels and titles."""
    document = MarkdownParser().parse(NESTED_FIXTURE, document_title="nested.md")

    class HeadingCollector(MarkdownAstVisitor):
        def __init__(self) -> None:
            self.headings: list[tuple[int, str]] = []

        def visit_section(self, section: SectionNode) -> None:
            if section.level > 0:
                self.headings.append((section.level, section.title))

    collector = HeadingCollector()
    collector.walk_document(document)

    assert collector.headings == [
        (1, "Document"),
        (2, "Section A"),
        (3, "Sub A"),
        (2, "Section B"),
    ]


def test_visitor_link_collector_subclass() -> None:
    """Subclass that collects all link destinations from inlines."""
    md = "# Links\n\nVisit [example](https://example.com) and [docs](https://docs.example.com).\n"
    document = MarkdownParser().parse(md, document_title="links.md")

    class LinkCollector(MarkdownAstVisitor):
        def __init__(self) -> None:
            self.links: list[str] = []

        def visit_inline(self, inline: MarkdownInline) -> None:
            if inline.kind == "link" and "destination" in inline.attrs:
                self.links.append(inline.attrs["destination"])

    collector = LinkCollector()
    collector.walk_document(document)

    assert collector.links == [
        "https://example.com",
        "https://docs.example.com",
    ]


def test_visitor_block_counter_subclass() -> None:
    """Subclass that counts blocks by kind."""
    document = MarkdownParser().parse(NESTED_FIXTURE, document_title="nested.md")

    class BlockCounter(MarkdownAstVisitor):
        def __init__(self) -> None:
            self.counts: dict[str, int] = {}

        def visit_block(self, block: MarkdownBlock) -> None:
            self.counts[block.kind] = self.counts.get(block.kind, 0) + 1

    counter = BlockCounter()
    counter.walk_document(document)

    assert counter.counts["paragraph"] >= 1
    assert counter.counts["code_fence"] == 1
    assert counter.counts["list"] >= 1


def test_visitor_empty_document() -> None:
    """Visitor handles a document with only the root section (no children, no blocks)."""
    document = MarkdownParser().parse("", document_title="empty.md")
    recorder = EventRecorder()
    recorder.walk_document(document)

    assert recorder.events == [
        ("enter_section", "empty.md", 0),
        ("depart_section", "empty.md", 0),
    ]


def test_visitor_walk_section_entry_point() -> None:
    """walk_section can start from an arbitrary section, not just the root."""
    document = MarkdownParser().parse(NESTED_FIXTURE, document_title="nested.md")

    class SectionTitleCollector(MarkdownAstVisitor):
        def __init__(self) -> None:
            self.titles: list[str] = []

        def visit_section(self, section: SectionNode) -> None:
            self.titles.append(section.title)

    collector = SectionTitleCollector()
    # Walk only Section A subtree
    section_a = document.root.children[0].children[0]
    collector.walk_section(section_a)

    assert collector.titles == ["Section A", "Sub A"]


def test_visitor_traversal_order_is_preorder() -> None:
    """enter is always before children; depart is always after children."""
    document = MarkdownParser().parse(NESTED_FIXTURE, document_title="nested.md")
    recorder = EventRecorder()
    recorder.walk_document(document)

    # For every enter_section at index i, the matching depart_section must be later
    section_stack: list[tuple[int, str, int | None]] = []
    for idx, event in enumerate(recorder.events):
        if event[0] == "enter_section":
            section_stack.append((idx, event[1], event[2]))
        elif event[0] == "depart_section":
            enter_idx, title, _level = section_stack.pop()
            assert event[1] == title
            assert event[2] == _level
            assert enter_idx < idx
    assert section_stack == []

    # Same for blocks
    block_stack: list[tuple[int, str, int | None]] = []
    for idx, event in enumerate(recorder.events):
        if event[0] == "enter_block":
            block_stack.append((idx, event[1], event[2]))
        elif event[0] == "depart_block":
            enter_idx, kind, _level = block_stack.pop()
            assert event[1] == kind
            assert enter_idx < idx
    assert block_stack == []


def test_visitor_importable_from_top_level() -> None:
    """MarkdownAstVisitor is importable from the top-level package."""
    from lumberjack import MarkdownAstVisitor as TopLevelVisitor

    assert TopLevelVisitor is MarkdownAstVisitor


def test_visitor_document_hooks_bracket_section_tree() -> None:
    """visit_document fires first; depart_document fires last."""
    document = MarkdownParser().parse(FLAT_FIXTURE, document_title="flat.md")

    class DocumentEventRecorder(MarkdownAstVisitor):
        def __init__(self) -> None:
            self.events: list[tuple[str, str]] = []

        def visit_document(self, document: DocumentAST) -> None:
            self.events.append(("enter_document", document.title))

        def depart_document(self, document: DocumentAST) -> None:
            self.events.append(("depart_document", document.title))

        def visit_section(self, section: SectionNode) -> None:
            self.events.append(("enter_section", section.title))

    recorder = DocumentEventRecorder()
    recorder.walk_document(document)

    assert recorder.events[0] == ("enter_document", "flat.md")
    assert recorder.events[-1] == ("depart_document", "flat.md")
    # Section events sit between the document hooks, never outside them.
    middle = recorder.events[1:-1]
    assert middle
    assert all(kind == "enter_section" for kind, _ in middle)
    titles = {title for _, title in recorder.events}
    assert "flat.md" in titles
    assert "Title" in titles


def test_visitor_metadata_reachable_in_visit_document() -> None:
    """visit_document can read document.metadata (YAML front matter)."""
    md = "---\ntitle: From Front Matter\nauthor: ada\n---\n\n# Heading\n\nBody.\n"
    document = MarkdownParser().parse(md, document_title="meta.md")

    class MetadataReader(MarkdownAstVisitor):
        def __init__(self) -> None:
            self.metadata: dict[str, object] = {}

        def visit_document(self, document: DocumentAST) -> None:
            self.metadata = dict(document.metadata)

    reader = MetadataReader()
    reader.walk_document(document)

    assert reader.metadata.get("title") == "From Front Matter"
    assert reader.metadata.get("author") == "ada"


def test_visitor_reference_definitions_reachable_in_visit_document() -> None:
    """visit_document can read document.reference_definitions."""
    md = "# Links\n\nSee [example][ref] and [ref][ref].\n\n[ref]: https://example.com\n"
    document = MarkdownParser().parse(md, document_title="refs.md")

    class RefReader(MarkdownAstVisitor):
        def __init__(self) -> None:
            self.refs: dict[str, dict[str, str]] = {}

        def visit_document(self, document: DocumentAST) -> None:
            self.refs = document.reference_definitions

    reader = RefReader()
    reader.walk_document(document)

    assert "ref" in reader.refs
    assert reader.refs["ref"]["destination"] == "https://example.com"


def test_visitor_document_title_reachable_in_visit_document() -> None:
    """visit_document can read document.title."""
    document = MarkdownParser().parse("# Body\n\nText.\n", document_title="title.md")

    class TitleReader(MarkdownAstVisitor):
        def __init__(self) -> None:
            self.title: str | None = None

        def visit_document(self, document: DocumentAST) -> None:
            self.title = document.title

    reader = TitleReader()
    reader.walk_document(document)

    assert reader.title == "title.md"


def test_visitor_depart_document_fires_after_blocks() -> None:
    """depart_document runs after every block has been walked."""
    document = MarkdownParser().parse(
        "# Title\n\nPara one.\n\nPara two.\n", document_title="order.md"
    )

    class OrderChecker(MarkdownAstVisitor):
        def __init__(self) -> None:
            self.block_count: int = 0
            self.count_at_depart: int | None = None
            self.title_at_depart: str | None = None

        def visit_block(self, block: MarkdownBlock) -> None:
            # Touching `block.kind` keeps the override honest about its argument
            # and mirrors how a real counter would bucket by kind.
            if block.kind:
                self.block_count += 1

        def depart_document(self, document: DocumentAST) -> None:
            self.count_at_depart = self.block_count
            self.title_at_depart = document.title

    checker = OrderChecker()
    checker.walk_document(document)

    assert checker.count_at_depart is not None
    assert checker.count_at_depart >= 2  # two paragraphs walked before depart
    assert checker.count_at_depart == checker.block_count
    assert checker.title_at_depart == "order.md"


def test_visitor_default_document_hooks_are_noops() -> None:
    """Bare visitor with default document hooks walks without raising."""
    document = MarkdownParser().parse("# Title\n\nBody.\n", document_title="noop.md")
    # No subclass overrides — should not raise
    MarkdownAstVisitor().walk_document(document)
