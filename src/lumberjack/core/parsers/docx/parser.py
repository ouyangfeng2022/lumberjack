from __future__ import annotations

from io import BytesIO
from typing import TYPE_CHECKING, Any, ClassVar

from ...models import (
    DocumentAST,
    MarkdownBlock,
    MarkdownInline,
    SectionNode,
)
from ...protocols import ParserProtocol

if TYPE_CHECKING:
    from docx.document import Document as DocxDocument


_HEADING_STYLE_PREFIXES = ("Heading", "heading", "标题")
_LIST_BULLET_PATTERNS = frozenset(
    {
        "List Bullet",
        "List Bullet 2",
        "List Bullet 3",
        "List Bullet 4",
        "List Bullet 5",
        "List Continue",
        "List Continue 2",
        "List Continue 3",
        "List Continue 4",
        "List Continue 5",
    }
)
_LIST_NUMBER_PATTERNS = frozenset(
    {
        "List Number",
        "List Number 2",
        "List Number 3",
        "List Number 4",
        "List Number 5",
        "List Number Field",
    }
)
_QUOTE_PATTERNS = frozenset({"Quote", "Intense Quote"})
_MONOSPACE_FAMILIES = frozenset({"Courier New", "Consolas", "Courier", "monospace"})


def _is_heading_style(style_name: str) -> bool:
    """Check if a paragraph style name represents a heading."""
    return any(style_name.startswith(prefix) for prefix in _HEADING_STYLE_PREFIXES)


def _heading_level_from_style(style_name: str) -> int:
    """Extract heading level from style name (e.g. 'Heading 1' -> 1)."""
    for prefix in _HEADING_STYLE_PREFIXES:
        if style_name.startswith(prefix):
            remainder = style_name[len(prefix) :].strip()
            if remainder:
                try:
                    return int(remainder)
                except ValueError:
                    return 1
            return 1
    return 1


def _is_list_bullet(style_name: str) -> bool:
    return style_name in _LIST_BULLET_PATTERNS


def _is_list_number(style_name: str) -> bool:
    return style_name in _LIST_NUMBER_PATTERNS


def _is_quote(style_name: str) -> bool:
    return style_name in _QUOTE_PATTERNS


def _is_code_paragraph(para: Any) -> bool:
    """Heuristic: detect code-like paragraphs by monospace font in all runs."""
    if not para.runs:
        return False
    for run in para.runs:
        font = run.font
        if font.name and font.name not in _MONOSPACE_FAMILIES:
            return False
        if not font.name:
            return False
    return True


def _runs_to_inlines(para: Any) -> tuple[MarkdownInline, ...]:
    """Convert paragraph runs to MarkdownInline nodes."""
    inlines: list[MarkdownInline] = []
    for run in para.runs:
        text = run.text
        if not text:
            continue
        font = run.font
        if font.bold and font.italic:
            inlines.append(
                MarkdownInline(
                    kind="strong",
                    children=(MarkdownInline(kind="emphasis", text=text),),
                )
            )
        elif font.bold:
            inlines.append(
                MarkdownInline(
                    kind="strong", children=(MarkdownInline(kind="text", text=text),)
                )
            )
        elif font.italic:
            inlines.append(MarkdownInline(kind="emphasis", text=text))
        elif run.font.underline:
            inlines.append(
                MarkdownInline(kind="text", text=text, attrs={"underline": True})
            )
        elif font.name and font.name in _MONOSPACE_FAMILIES:
            inlines.append(
                MarkdownInline(kind="code_span", text=text, attrs={"literal": text})
            )
        else:
            inlines.append(MarkdownInline(kind="text", text=text))
    return tuple(inlines)


def _render_table(table: Any) -> str:
    """Render a DOCX table as Markdown pipe table text."""
    rows_data: list[list[str]] = []
    for row in table.rows:
        cells = [cell.text.replace("\n", " ").strip() for cell in row.cells]
        rows_data.append(cells)

    if not rows_data:
        return ""

    # Normalize column count
    max_cols = max(len(r) for r in rows_data)
    for row in rows_data:
        while len(row) < max_cols:
            row.append("")

    lines: list[str] = []
    for i, row in enumerate(rows_data):
        line = "| " + " | ".join(row) + " |"
        lines.append(line)
        if i == 0:
            sep = "| " + " | ".join("---" for _ in row) + " |"
            lines.append(sep)

    return "\n".join(lines)


class DocxParser(ParserProtocol[bytes]):
    """Parse DOCX documents into DocumentAST.

    Maps DOCX structural elements to the same DocumentAST model used by
    the Markdown parser, enabling reuse of all existing splitters.

    Block kind mapping:
        - Heading styles  → SectionNode hierarchy
        - Normal paragraphs → ``paragraph``
        - Tables            → ``table``
        - List Bullet/Number → ``list`` with ``list_item`` children
        - Monospace paragraphs → ``code_block``
        - Quote style       → ``blockquote``
    """

    default_block_kinds: ClassVar[frozenset[str]] = frozenset(
        {
            "paragraph",
            "table",
            "list",
            "list_item",
            "code_block",
            "blockquote",
        }
    )

    @property
    def block_kinds(self) -> frozenset[str]:
        """Block kinds this parser can produce."""
        return self.default_block_kinds

    def parse(
        self,
        data: bytes,
        *,
        document_title: str | None = None,
        document_metadata: dict[str, object] | None = None,
        max_heading_level: int | None = None,  # noqa: ARG002
    ) -> DocumentAST:
        """Parse DOCX binary data into a DocumentAST.

        Args:
            data: Raw DOCX file content.
            document_title: Optional override for the document title.
            document_metadata: Optional metadata dict merged into the result.
            max_heading_level: Currently ignored. Accepted for protocol parity
                with the Markdown and HTML parsers; DOCX heading levels are
                determined by paragraph styles and are not remapped at parse
                time (may be supported in the future).
        """
        from docx import Document

        if not isinstance(data, bytes | bytearray):
            msg = f"DocxParser.parse expects bytes, got {type(data).__name__}"
            raise TypeError(msg)

        if document_metadata is None:
            document_metadata = {}

        doc = Document(BytesIO(data))

        # Extract core properties as metadata
        core_props = doc.core_properties
        if core_props.title and "title" not in document_metadata:
            document_metadata.setdefault("title", core_props.title)
        if core_props.author:
            document_metadata.setdefault("author", core_props.author)

        root = SectionNode(level=0, title="")
        section_stack: list[SectionNode] = [root]
        element_counter = 0

        # Iterate document body elements in order
        for element in doc.element.body:
            tag = element.tag.split("}")[-1] if "}" in element.tag else element.tag

            if tag == "p":
                para = self._paragraph_from_element(doc, element)
                if para is None:
                    continue
                style_name = para.style.name if para.style else "Normal"

                if _is_heading_style(style_name):
                    level = _heading_level_from_style(style_name)
                    title_text = para.text.strip()
                    if not title_text:
                        continue
                    title_inlines = _runs_to_inlines(para)
                    element_counter += 1

                    while section_stack and section_stack[-1].level >= level:
                        section_stack.pop()
                    parent = section_stack[-1]
                    section = SectionNode(
                        level=level,
                        title=title_text,
                        path=(*parent.path, (level, title_text)),
                        index=len(parent.children),
                        start_line=element_counter,
                        title_inlines=title_inlines,
                    )
                    parent.add_child(section)
                    section_stack.append(section)

                elif _is_list_bullet(style_name) or _is_list_number(style_name):
                    # Accumulate consecutive list paragraphs into a list block
                    element_counter += 1
                    list_children: list[MarkdownBlock] = []
                    list_text_parts: list[str] = []

                    list_ordered = _is_list_number(style_name)
                    item_text = para.text.strip()
                    item_inlines = _runs_to_inlines(para)
                    element_counter += 1
                    list_children.append(
                        MarkdownBlock(
                            kind="list_item",
                            text=item_text,
                            start_line=element_counter,
                            end_line=element_counter,
                            inlines=item_inlines,
                        )
                    )
                    list_text_parts.append(
                        f"- {item_text}" if not list_ordered else f"1. {item_text}"
                    )

                    list_text = "\n".join(list_text_parts)
                    section_stack[-1].add_block(
                        MarkdownBlock(
                            kind="list",
                            text=list_text,
                            start_line=element_counter,
                            end_line=element_counter,
                            children=tuple(list_children),
                            attrs={"ordered": list_ordered},
                        )
                    )

                elif _is_quote(style_name):
                    element_counter += 1
                    text = para.text.strip()
                    inlines = _runs_to_inlines(para)
                    rendered = f"> {text}" if text else ""
                    section_stack[-1].add_block(
                        MarkdownBlock(
                            kind="blockquote",
                            text=rendered,
                            start_line=element_counter,
                            end_line=element_counter,
                            inlines=inlines,
                        )
                    )

                elif _is_code_paragraph(para):
                    element_counter += 1
                    code_text = para.text
                    section_stack[-1].add_block(
                        MarkdownBlock(
                            kind="code_block",
                            text=f"```\n{code_text}\n```",
                            start_line=element_counter,
                            end_line=element_counter,
                            attrs={"literal": code_text},
                        )
                    )

                else:
                    # Normal paragraph
                    text = para.text.strip()
                    if not text:
                        continue
                    element_counter += 1
                    inlines = _runs_to_inlines(para)
                    section_stack[-1].add_block(
                        MarkdownBlock(
                            kind="paragraph",
                            text=text,
                            start_line=element_counter,
                            end_line=element_counter,
                            inlines=inlines,
                        )
                    )

            elif tag == "tbl":
                table = self._table_from_element(doc, element)
                if table is None:
                    continue
                element_counter += 1
                rendered = _render_table(table)
                if rendered:
                    section_stack[-1].add_block(
                        MarkdownBlock(
                            kind="table",
                            text=rendered,
                            start_line=element_counter,
                            end_line=element_counter,
                        )
                    )

        final_title = self._resolve_document_title(document_title, doc, root)
        root.title = final_title

        return DocumentAST(
            title=final_title,
            source="",
            root=root,
            metadata=document_metadata,
        )

    def _paragraph_from_element(self, doc: DocxDocument, element: Any) -> Any | None:
        """Get a paragraph object from its XML element."""
        from docx.text.paragraph import Paragraph

        try:
            return Paragraph(element, doc)
        except Exception:
            return None

    def _table_from_element(self, doc: DocxDocument, element: Any) -> Any | None:
        """Get a table object from its XML element."""
        from docx.table import Table

        try:
            return Table(element, doc)
        except Exception:
            return None

    def _resolve_document_title(
        self,
        document_title: str | None,
        doc: DocxDocument,
        root: SectionNode,
    ) -> str:
        """Resolve document title: user-provided > core properties > first H1 > Anonymous."""
        if document_title is not None:
            return document_title

        core_props = doc.core_properties
        if core_props.title and core_props.title.strip():
            return core_props.title.strip()

        h1_title = self._first_h1_title(root)
        if h1_title is not None:
            return h1_title

        return "Anonymous"

    @staticmethod
    def _first_h1_title(root: SectionNode) -> str | None:
        """Return the title of the first level-1 heading section, or None."""
        for child in root.children:
            if child.level == 1:
                return child.title
        return None
