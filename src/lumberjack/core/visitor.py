from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .models import DocumentAST, MarkdownBlock, MarkdownInline, SectionNode


class MarkdownAstVisitor:
    """Visitor for traversing a parsed :class:`DocumentAST` tree.

    Provides enter/depart hooks for each node type (section, block, inline).
    Subclass and override the ``visit_*`` / ``depart_*`` methods to implement
    custom tree processing — collecting headings, extracting links, counting
    block types, validating structure, etc.

    Works with any :class:`DocumentAST`, regardless of whether it was produced
    by the Markdown parser or the DOCX parser.

    Traversal order is **pre-order** (enter → children → depart):

    * ``visit_section`` → blocks → child sections → ``depart_section``
    * ``visit_block``   → child blocks → inlines → ``depart_block``
    * ``visit_inline``  → child inlines → ``depart_inline``

    Usage::

        from lumberjack.core import MarkdownAstVisitor
        from lumberjack.core.markdown.parser import MarkdownItParser

        class HeadingCollector(MarkdownAstVisitor):
            def __init__(self):
                self.headings: list[tuple[int, str]] = []

            def visit_section(self, section: SectionNode) -> None:
                if section.level > 0:
                    self.headings.append((section.level, section.title))

        parser = MarkdownItParser()
        document = parser.parse("# Title\\n\\nParagraph")
        collector = HeadingCollector()
        collector.walk_document(document)
        print(collector.headings)  # [(1, "Title")]
    """

    # ------------------------------------------------------------------
    # Entry points
    # ------------------------------------------------------------------

    def walk_document(self, document: DocumentAST) -> None:
        """Walk the full document tree starting from the root section."""
        self.walk_section(document.root)

    def walk_section(self, section: SectionNode) -> None:
        """Recursively visit a section's blocks and child sections."""
        self.visit_section(section)
        for block in section.blocks:
            self.walk_block(block)
        for child in section.children:
            self.walk_section(child)
        self.depart_section(section)

    def walk_block(self, block: MarkdownBlock) -> None:
        """Visit a block, its nested child blocks, then its inlines."""
        self.visit_block(block)
        for child in block.children:
            self.walk_block(child)
        for inline in block.inlines:
            self.walk_inline(inline)
        self.depart_block(block)

    def walk_inline(self, inline: MarkdownInline) -> None:
        """Visit an inline node and its nested children."""
        self.visit_inline(inline)
        for child in inline.children:
            self.walk_inline(child)
        self.depart_inline(inline)

    # ------------------------------------------------------------------
    # Hooks — override in subclasses
    # ------------------------------------------------------------------

    def visit_section(self, section: SectionNode) -> None:
        """Hook called when *entering* a section node."""

    def depart_section(self, section: SectionNode) -> None:
        """Hook called when *leaving* a section node."""

    def visit_block(self, block: MarkdownBlock) -> None:
        """Hook called when *entering* a block node."""

    def depart_block(self, block: MarkdownBlock) -> None:
        """Hook called when *leaving* a block node."""

    def visit_inline(self, inline: MarkdownInline) -> None:
        """Hook called when *entering* an inline node."""

    def depart_inline(self, inline: MarkdownInline) -> None:
        """Hook called when *leaving* an inline node."""
