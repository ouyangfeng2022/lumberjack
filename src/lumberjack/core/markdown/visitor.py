from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ..models import DocumentAST, MarkdownBlock, SectionNode


class MarkdownAstVisitor:
    """Small visitor hook set for future extensions."""

    def visit_document(self, document: DocumentAST):
        """Walk the document's root section and all its descendants."""
        self.walk_section(document.root)

    def walk_section(self, section: SectionNode):
        """Recursively visit a section's blocks and children."""
        self.visit_section(section)
        for block in section.blocks:
            self.visit_block(block, parent=section)
        for child in section.children:
            self.walk_section(child)

    def visit_section(self, section: SectionNode):
        """Hook called for each section node. Override in subclasses."""
        ...

    def visit_block(self, block: MarkdownBlock, *, parent: SectionNode):
        """Hook called for each block within a section. Override in subclasses."""
        ...
