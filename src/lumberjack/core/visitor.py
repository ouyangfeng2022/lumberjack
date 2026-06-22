from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .models import DocumentAST, MarkdownBlock, MarkdownInline, SectionNode


def _parse_table_rows(block_text: str) -> list[list[str]]:
    """Split pipe-delimited markdown table text into rows of cell strings.

    Returns:
        List of rows, each row a list of cell strings. The delimiter
        row (``|---|---|``) is excluded from the result.
    """
    lines = block_text.strip().split("\n")
    rows: list[list[str]] = []
    for line in lines:
        stripped = line.strip()
        if not stripped.startswith("|"):
            continue
        cells = [c.strip() for c in stripped.strip("|").split("|")]
        rows.append(cells)
    return rows


class AstVisitor:
    """Visitor for traversing a parsed :class:`DocumentAST` tree.

    Provides enter/depart hooks for each node type (section, block, inline).
    Subclass and override the ``visit_*`` / ``depart_*`` methods to implement
    custom tree processing — collecting headings, extracting links, counting
    block types, validating structure, etc.

    Works with any :class:`DocumentAST`, regardless of whether it was produced
    by the Markdown, DOCX, or HTML parser.

    Traversal order is **pre-order** (enter → children → depart):

    * ``visit_section`` → blocks → child sections → ``depart_section``
    * ``visit_block``   → child blocks → inlines → ``depart_block``
    * ``visit_inline``  → child inlines → ``depart_inline``

    Usage::

        from lumberjack.core import AstVisitor
        from lumberjack.core.parsers.markdown.parser import MarkdownItParser

        class HeadingCollector(AstVisitor):
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
        """Walk the full document tree.

        Fires :meth:`visit_document` before the section tree and
        :meth:`depart_document` after it, so subclasses can read
        ``document.title``, ``document.metadata``, and
        ``document.reference_definitions`` without touching ``document.root``.

        Returning ``False`` from :meth:`visit_document` skips the section tree;
        :meth:`depart_document` still fires.
        """
        descend = self.visit_document(document)
        if descend is not False:
            self.walk_section(document.root)
        self.depart_document(document)

    def walk_section(self, section: SectionNode) -> None:
        """Recursively visit a section's blocks and child sections.

        Returning ``False`` from :meth:`visit_section` skips this section's
        blocks and child sections; :meth:`depart_section` still fires.
        """
        descend = self.visit_section(section)
        if descend is not False:
            for block in section.blocks:
                self.walk_block(block)
            for child in section.children:
                self.walk_section(child)
        self.depart_section(section)

    def walk_block(self, block: MarkdownBlock) -> None:
        """Visit a block, its nested child blocks, then its inlines.

        Returning ``False`` from :meth:`visit_block` skips this block's
        nested child blocks and inlines; :meth:`depart_block` still fires.
        """
        descend = self.visit_block(block)
        if descend is not False:
            for child in block.children:
                self.walk_block(child)
            for inline in block.inlines:
                self.walk_inline(inline)
        # --- structured-content dispatch (fires even when pruned) ---
        kind = block.kind
        if kind == "table" or kind == "html_table":
            self._walk_table_cells(block)
        elif kind == "code_fence":
            literal = block.attrs.get("literal", "")
            language = block.attrs.get("language", "")
            self.visit_code_content(literal, language)
            self.depart_code_content(literal, language)
        elif kind == "math_block":
            literal = block.attrs.get("literal", "")
            self.visit_math_content(literal)
            self.depart_math_content(literal)
        self.depart_block(block)

    def walk_inline(self, inline: MarkdownInline) -> None:
        """Visit an inline node and its nested children.

        Returning ``False`` from :meth:`visit_inline` skips this inline's
        nested children; :meth:`depart_inline` still fires.
        """
        descend = self.visit_inline(inline)
        if descend is not False:
            for child in inline.children:
                self.walk_inline(child)
        self.depart_inline(inline)

    # ------------------------------------------------------------------
    # Structured-content helpers (called by walk_block)
    # ------------------------------------------------------------------

    def _walk_table_cells(self, block: MarkdownBlock) -> None:
        """Walk table cells for markdown or HTML table blocks."""
        if block.kind == "html_table":
            self._walk_html_table_cells(block.text)
            return
        rows = _parse_table_rows(block.text)
        if len(rows) < 3:
            return  # no delimiter row — not a valid table
        # Row 0 = header, Row 1 = delimiter (skip), Rows 2+ = data
        for col_idx, cell_text in enumerate(rows[0]):
            self.visit_table_cell(0, col_idx, cell_text, is_header=True)
            self.depart_table_cell(0, col_idx, cell_text, is_header=True)
        for row_idx, row in enumerate(rows[2:], start=1):
            for col_idx, cell_text in enumerate(row):
                self.visit_table_cell(row_idx, col_idx, cell_text, is_header=False)
                self.depart_table_cell(row_idx, col_idx, cell_text, is_header=False)

    def _walk_html_table_cells(self, html_content: str) -> None:
        """Walk cells in an HTML table using HTMLTableParser."""
        from .parsers.html.table_parser import HTMLTableParser

        parser = HTMLTableParser()
        tables = parser.extract_tables(html_content)
        for table in tables:
            for header_row in table.headers:
                for col_idx, cell in enumerate(header_row.cells):
                    self.visit_table_cell(0, col_idx, cell.text, is_header=True)
                    self.depart_table_cell(0, col_idx, cell.text, is_header=True)
            for row_idx, row in enumerate(table.rows, start=1):
                for col_idx, cell in enumerate(row.cells):
                    self.visit_table_cell(row_idx, col_idx, cell.text, is_header=False)
                    self.depart_table_cell(row_idx, col_idx, cell.text, is_header=False)

    # ------------------------------------------------------------------
    # Hooks — override in subclasses
    # ------------------------------------------------------------------

    def visit_section(self, section: SectionNode) -> bool | None:
        """Hook called when *entering* a section node.

        Return ``False`` to skip this section's blocks and child sections.
        :meth:`depart_section` still fires.
        """

    def depart_section(self, section: SectionNode) -> None:
        """Hook called when *leaving* a section node."""

    def visit_block(self, block: MarkdownBlock) -> bool | None:
        """Hook called when *entering* a block node.

        Return ``False`` to skip this block's nested child blocks and
        inlines. :meth:`depart_block` still fires.
        """

    def depart_block(self, block: MarkdownBlock) -> None:
        """Hook called when *leaving* a block node."""

    def visit_inline(self, inline: MarkdownInline) -> bool | None:
        """Hook called when *entering* an inline node.

        Return ``False`` to skip this inline's nested children.
        :meth:`depart_inline` still fires.
        """

    def depart_inline(self, inline: MarkdownInline) -> None:
        """Hook called when *leaving* an inline node."""

    def visit_table_cell(
        self, row_idx: int, col_idx: int, text: str, is_header: bool
    ) -> None:
        """Hook called for each cell in a table or html_table block.

        Args:
            row_idx: 0-based row index (0 = header, 1+ = data rows).
            col_idx: 0-based column index within the row.
            text: Cell text content (markup stripped).
            is_header: Whether this cell belongs to the header row.
        """

    def depart_table_cell(
        self, row_idx: int, col_idx: int, text: str, is_header: bool
    ) -> None:
        """Hook called after a table cell has been visited."""

    def visit_code_content(self, literal: str, language: str) -> None:
        """Hook called for each code_fence block.

        Args:
            literal: Code text content (from ``attrs["literal"]``).
            language: Language tag (from ``attrs["language"]``), or ``""``.
        """

    def depart_code_content(self, literal: str, language: str) -> None:
        """Hook called after code content has been visited."""

    def visit_math_content(self, literal: str) -> None:
        """Hook called for each math_block block.

        Args:
            literal: Math expression text (from ``attrs["literal"]``).
        """

    def depart_math_content(self, literal: str) -> None:
        """Hook called after math content has been visited."""

    def visit_document(self, document: DocumentAST) -> bool | None:
        """Hook called when *entering* a document.

        Read ``document.title``, ``document.metadata``, and
        ``document.reference_definitions`` here before the section tree
        is walked.

        Return ``False`` to skip the entire section tree.
        :meth:`depart_document` still fires.
        """

    def depart_document(self, document: DocumentAST) -> None:
        """Hook called when the full document tree has been walked.

        Use for finalization (emit collected data, log summaries).
        """
