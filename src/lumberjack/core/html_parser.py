"""HTML document parser and table helpers."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from html.parser import HTMLParser as _StdlibHTMLParser
from typing import Any, ClassVar

from .models import DocumentAST, MarkdownBlock, MarkdownInline, SectionNode


def _clean_text(text: str) -> str:
    """Collapse HTML text whitespace into a Markdown-like paragraph string."""
    return " ".join(text.split())


def _line_offsets(source: str) -> list[int]:
    """Return the absolute offset where each 1-based line starts."""
    offsets = [0]
    offset = 0
    for line in source.splitlines(keepends=True):
        offset += len(line)
        offsets.append(offset)
    return offsets


def _attrs_dict(attrs: list[tuple[str, str | None]]) -> dict[str, str]:
    return {name.lower(): value or "" for name, value in attrs}


@dataclass(slots=True)
class _TextCollector:
    kind: str
    start_line: int | None
    text_parts: list[str] = field(default_factory=list)
    inlines: list[MarkdownInline] = field(default_factory=list)
    attrs: dict[str, Any] = field(default_factory=dict)

    def add_text(self, text: str, inline_kind: str = "text") -> None:
        if not text:
            return
        self.text_parts.append(text)
        self.inlines.append(MarkdownInline(kind=inline_kind, text=text))

    def rendered_text(self) -> str:
        return _clean_text("".join(self.text_parts))


@dataclass(slots=True)
class _ListItem:
    text: str
    start_line: int | None
    end_line: int | None
    inlines: tuple[MarkdownInline, ...]


@dataclass(slots=True)
class _ListCollector:
    ordered: bool
    start_line: int | None
    items: list[_ListItem] = field(default_factory=list)


@dataclass(slots=True)
class _TableCollector:
    start_offset: int
    start_line: int | None
    depth: int = 1


class _HTMLDocumentBuilder(_StdlibHTMLParser):
    """Event parser that normalizes HTML into the shared DocumentAST model."""

    _BLOCK_TAGS: ClassVar[frozenset[str]] = frozenset({"p", "pre", "blockquote"})
    _HEADING_TAGS: ClassVar[frozenset[str]] = frozenset(
        {"h1", "h2", "h3", "h4", "h5", "h6"}
    )
    _INLINE_KIND_BY_TAG: ClassVar[dict[str, str]] = {
        "strong": "strong",
        "b": "strong",
        "em": "emphasis",
        "i": "emphasis",
        "code": "code_span",
        "a": "link",
    }

    def __init__(
        self,
        *,
        source: str,
        document_title: str | None,
        document_metadata: dict[str, object],
        max_heading_level: int | None,
    ) -> None:
        super().__init__(convert_charrefs=True)
        self._source = source
        self._line_offsets = _line_offsets(source)
        self._document_title = document_title
        self._metadata = dict(document_metadata)
        self._max_heading_level = max_heading_level
        self._root = SectionNode(level=0, title="")
        self._section_stack: list[SectionNode] = [self._root]
        self._heading: _TextCollector | None = None
        self._block: _TextCollector | None = None
        self._list_stack: list[_ListCollector] = []
        self._list_item: _TextCollector | None = None
        self._table_stack: list[_TableCollector] = []
        self._title_parts: list[str] = []
        self._collect_title = False
        self._skip_depth = 0
        self._head_depth = 0
        self._body_seen = False
        self._inline_stack: list[str] = []

    def build(self) -> DocumentAST:
        self.feed(self._source)
        self.close()
        self._close_block(self.getpos()[0])
        final_title = self._resolve_document_title()
        self._root.title = final_title
        return DocumentAST(
            title=final_title,
            source=self._source,
            root=self._root,
            metadata=self._metadata,
        )

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        tag = tag.lower()
        line, column = self.getpos()
        if tag == "head":
            self._head_depth += 1
            return
        if tag == "body":
            self._body_seen = True
            return
        if tag in {"script", "style"}:
            self._skip_depth += 1
            return
        if tag == "title":
            self._collect_title = True
            self._title_parts = []
            return
        if tag == "meta":
            self._capture_meta(attrs)
            return
        if self._skip_depth or self._head_depth:
            return

        if tag == "table":
            if self._table_stack:
                self._table_stack[-1].depth += 1
            else:
                self._close_block(line)
                self._table_stack.append(
                    _TableCollector(
                        start_offset=self._absolute_offset(line, column),
                        start_line=line,
                    )
                )
            return
        if self._table_stack:
            return

        if tag in self._HEADING_TAGS:
            self._close_block(line)
            self._heading = _TextCollector(
                kind=tag,
                start_line=line,
                attrs={"level": int(tag[1])},
            )
            return
        if tag in {"ul", "ol"}:
            self._close_block(line)
            self._list_stack.append(
                _ListCollector(ordered=tag == "ol", start_line=line)
            )
            return
        if tag == "li":
            self._list_item = _TextCollector(kind="list_item", start_line=line)
            return
        if tag in self._BLOCK_TAGS and self._list_item is None:
            self._close_block(line)
            kind_by_tag = {
                "blockquote": "blockquote",
                "p": "paragraph",
                "pre": "code_block",
            }
            kind = kind_by_tag[tag]
            self._block = _TextCollector(kind=kind, start_line=line)
            return
        if tag == "br":
            self._add_text("\n")
            return
        if tag == "img":
            alt = _attrs_dict(attrs).get("alt", "")
            if alt:
                self._add_text(alt, "image")
            return
        if tag in self._INLINE_KIND_BY_TAG:
            self._inline_stack.append(self._INLINE_KIND_BY_TAG[tag])

    def handle_endtag(self, tag: str) -> None:
        tag = tag.lower()
        line, column = self.getpos()
        if tag == "head":
            self._head_depth = max(0, self._head_depth - 1)
            return
        if tag in {"script", "style"}:
            self._skip_depth = max(0, self._skip_depth - 1)
            return
        if tag == "title":
            self._collect_title = False
            title = _clean_text("".join(self._title_parts))
            if title:
                self._metadata.setdefault("title", title)
            return
        if self._skip_depth or self._head_depth:
            return

        if self._table_stack:
            if tag == "table":
                table = self._table_stack[-1]
                table.depth -= 1
                if table.depth == 0:
                    self._table_stack.pop()
                    self._add_table_block(table, self._end_tag_offset(line, column))
            return

        if self._heading is not None and tag == self._heading.kind:
            self._add_heading_or_paragraph(line)
            return
        if self._block is not None and tag in self._BLOCK_TAGS:
            self._close_block(line)
            return
        if self._list_item is not None and tag == "li":
            self._close_list_item(line)
            return
        if tag in {"ul", "ol"}:
            self._close_list(line)
            return
        if tag in self._INLINE_KIND_BY_TAG and self._inline_stack:
            self._inline_stack.pop()

    def handle_data(self, data: str) -> None:
        if self._collect_title:
            self._title_parts.append(data)
            return
        if self._skip_depth or self._head_depth or self._table_stack:
            return
        self._add_text(data)

    def _capture_meta(self, attrs: list[tuple[str, str | None]]) -> None:
        attrs_by_name = _attrs_dict(attrs)
        key = attrs_by_name.get("name") or attrs_by_name.get("property")
        content = attrs_by_name.get("content")
        if key and content:
            self._metadata.setdefault(key.lower(), content)

    def _add_text(self, text: str, inline_kind: str | None = None) -> None:
        if not text:
            return
        kind = inline_kind or (self._inline_stack[-1] if self._inline_stack else "text")
        if self._heading is not None:
            self._heading.add_text(text, kind)
        elif self._list_item is not None:
            self._list_item.add_text(text, kind)
        elif self._block is not None:
            self._block.add_text(text, kind)
        elif text.strip() and self._body_seen:
            line = self.getpos()[0]
            self._block = _TextCollector(kind="paragraph", start_line=line)
            self._block.add_text(text, kind)

    def _add_heading_or_paragraph(self, end_line: int) -> None:
        if self._heading is None:
            return
        title = self._heading.rendered_text()
        if not title:
            self._heading = None
            return
        level = int(self._heading.attrs["level"])
        if self._max_heading_level is not None and level > self._max_heading_level:
            self._section_stack[-1].add_block(
                MarkdownBlock(
                    kind="paragraph",
                    text=title,
                    start_line=self._heading.start_line,
                    end_line=end_line,
                    inlines=tuple(self._heading.inlines),
                )
            )
            self._heading = None
            return

        while self._section_stack and self._section_stack[-1].level >= level:
            self._section_stack.pop()
        parent = self._section_stack[-1]
        section = SectionNode(
            level=level,
            title=title,
            path=(*parent.path, (level, title)),
            index=len(parent.children),
            start_line=self._heading.start_line,
            title_inlines=tuple(self._heading.inlines),
        )
        parent.add_child(section)
        self._section_stack.append(section)
        self._heading = None

    def _close_block(self, end_line: int) -> None:
        if self._block is None:
            return
        text = self._block.rendered_text()
        if text:
            kind = self._block.kind
            if kind == "blockquote":
                text = "\n".join(f"> {line}" for line in text.splitlines())
            if kind == "code_block":
                literal = text
                text = f"```\n{literal}\n```"
                self._block.attrs["literal"] = literal
            self._section_stack[-1].add_block(
                MarkdownBlock(
                    kind=kind,
                    text=text,
                    start_line=self._block.start_line,
                    end_line=end_line,
                    inlines=tuple(self._block.inlines),
                    attrs=self._block.attrs,
                )
            )
        self._block = None

    def _close_list_item(self, end_line: int) -> None:
        if self._list_item is None:
            return
        text = self._list_item.rendered_text()
        if text and self._list_stack:
            self._list_stack[-1].items.append(
                _ListItem(
                    text=text,
                    start_line=self._list_item.start_line,
                    end_line=end_line,
                    inlines=tuple(self._list_item.inlines),
                )
            )
        self._list_item = None

    def _close_list(self, end_line: int) -> None:
        if not self._list_stack:
            return
        list_block = self._list_stack.pop()
        if not list_block.items:
            return
        children = tuple(
            MarkdownBlock(
                kind="list_item",
                text=item.text,
                start_line=item.start_line,
                end_line=item.end_line,
                inlines=item.inlines,
            )
            for item in list_block.items
        )
        marker = "1." if list_block.ordered else "-"
        text = "\n".join(f"{marker} {item.text}" for item in list_block.items)
        self._section_stack[-1].add_block(
            MarkdownBlock(
                kind="list",
                text=text,
                start_line=list_block.start_line,
                end_line=end_line,
                children=children,
                attrs={"ordered": list_block.ordered},
            )
        )

    def _add_table_block(self, table: _TableCollector, end_offset: int) -> None:
        table_html = self._source[table.start_offset : end_offset].strip()
        if not table_html:
            return
        self._section_stack[-1].add_block(
            MarkdownBlock(
                kind="html_table",
                text=table_html,
                start_line=table.start_line,
                end_line=self.getpos()[0],
                attrs={"literal": table_html},
            )
        )

    def _resolve_document_title(self) -> str:
        if self._document_title:
            return self._document_title
        metadata_title = self._metadata.get("title")
        if isinstance(metadata_title, str) and metadata_title.strip():
            return metadata_title.strip()
        for section in self._root.children:
            if section.level == 1 and section.title:
                return section.title
        return "Anonymous"

    def _absolute_offset(self, line: int, column: int) -> int:
        if line <= 0:
            return column
        if line - 1 >= len(self._line_offsets):
            return len(self._source)
        return min(len(self._source), self._line_offsets[line - 1] + column)

    def _end_tag_offset(self, line: int, column: int) -> int:
        start = self._absolute_offset(line, column)
        tag_end = self._source.find(">", start)
        return len(self._source) if tag_end == -1 else tag_end + 1


class HTMLParser:
    """Parse HTML documents into the shared ``DocumentAST`` model.

    The parser mirrors the public parser shape used by Markdown and DOCX:
    it exposes ``block_kinds`` and returns a heading-tree ``DocumentAST`` so
    the existing splitters can operate on HTML input without a separate path.
    """

    _BLOCK_KINDS: frozenset[str] = frozenset(
        {
            "paragraph",
            "blockquote",
            "list",
            "list_item",
            "code_block",
            "html_block",
            "html_table",
            "front_matter",
        }
    )

    @property
    def block_kinds(self) -> frozenset[str]:
        """Block kinds this parser can produce."""
        return self._BLOCK_KINDS

    def parse(
        self,
        text: str,
        *,
        document_title: str | None = None,
        document_metadata: dict[str, object] | None = None,
        max_heading_level: int | None = None,
    ) -> DocumentAST:
        """Parse raw HTML text into a ``DocumentAST``.

        Args:
            text: Raw HTML source.
            document_title: Optional override for the document title.
            document_metadata: Optional metadata dict merged into the result.
            max_heading_level: Maximum heading level to parse as sections.
                Headings deeper than this level are treated as paragraph blocks.
        """
        builder = _HTMLDocumentBuilder(
            source=text,
            document_title=document_title,
            document_metadata=document_metadata or {},
            max_heading_level=max_heading_level,
        )
        return builder.build()


@dataclass(slots=True, frozen=True)
class HTMLTableCell:
    """HTML table cell.

    Attributes:
        text: Cell text content (with tags stripped).
        raw_html: Raw HTML content of the cell.
        is_header: Whether this cell is a header cell (th).
        row_span: Number of rows this cell spans.
        col_span: Number of columns this cell spans.
    """

    text: str
    raw_html: str
    is_header: bool
    row_span: int = 1
    col_span: int = 1


@dataclass(slots=True, frozen=True)
class HTMLTableRow:
    """HTML table row.

    Attributes:
        cells: List of cells in this row.
        raw_html: Raw HTML content of the row.
        is_header: Whether this is a header row (contains th elements).
    """

    cells: tuple[HTMLTableCell, ...]
    raw_html: str
    is_header: bool


@dataclass(slots=True, frozen=True)
class HTMLTable:
    """Parsed HTML table.

    Attributes:
        headers: List of header rows (if present).
        rows: List of data rows.
        raw_html: Raw HTML content of the table.
        caption: Table caption text (if present).
    """

    headers: tuple[HTMLTableRow, ...]
    rows: tuple[HTMLTableRow, ...]
    raw_html: str
    caption: str = ""


class HTMLTableParser:
    """Parser for extracting HTML tables from HTML block content.

    This parser detects and extracts <table> elements from HTML content,
    parsing their structure (headers, rows, cells) for further processing
    by the document splitter.
    """

    # HTML tag parsing patterns
    TABLE_OPEN_RE = re.compile(r"<table\b[^>]*>", re.IGNORECASE)
    TABLE_CLOSE_RE = re.compile(r"</table\s*>", re.IGNORECASE)
    TR_OPEN_RE = re.compile(r"<tr\b[^>]*>", re.IGNORECASE)
    TR_CLOSE_RE = re.compile(r"</tr\s*>", re.IGNORECASE)
    TH_RE = re.compile(r"<th\b[^>]*>(.*?)</th\s*>", re.IGNORECASE | re.DOTALL)
    TD_RE = re.compile(r"<td\b[^>]*>(.*?)</td\s*>", re.IGNORECASE | re.DOTALL)
    CAPTION_RE = re.compile(
        r"<caption\b[^>]*>(.*?)</caption\s*>", re.IGNORECASE | re.DOTALL
    )

    # Attribute extraction patterns
    ROWSPAN_RE = re.compile(r'\browspan\s*=\s*["\']?(\d+)["\']?', re.IGNORECASE)
    COLSPAN_RE = re.compile(r'\bcolspan\s*=\s*["\']?(\d+)["\']?', re.IGNORECASE)

    def __init__(self) -> None:
        self._strip_tags_re = re.compile(r"<[^>]+>")

    def extract_tables(self, html_content: str) -> list[HTMLTable]:
        """Extract all HTML tables from the given HTML content.

        Args:
            html_content: Raw HTML content (e.g., from html_block).

        Returns:
            List of parsed HTMLTable objects in document order.
        """
        tables: list[HTMLTable] = []
        for table_match in self.TABLE_OPEN_RE.finditer(html_content):
            table_start = table_match.start()
            table_end = self._find_matching_table_close(html_content, table_start)
            if table_end is None:
                continue

            table_html = html_content[table_start:table_end]
            parsed_table = self._parse_table(table_html)
            tables.append(parsed_table)

        return tables

    def contains_table(self, html_content: str) -> bool:
        """Check if the HTML content contains any table elements.

        Args:
            html_content: Raw HTML content.

        Returns:
            True if at least one <table> element is found.
        """
        return bool(self.TABLE_OPEN_RE.search(html_content))

    def to_markdown_table(self, table: HTMLTable) -> str:
        """Convert an HTML table to markdown table format.

        This converts the parsed HTML table back to markdown format,
        which can then be processed by the existing markdown table
        splitting logic.

        Args:
            table: Parsed HTML table.

        Returns:
            Markdown-formatted table string.
        """
        lines: list[str] = []

        # Add caption if present
        if table.caption:
            lines.append(f"*{table.caption}*")

        if not table.rows:
            return "\n".join(lines) if lines else ""

        # Use first header row if available, otherwise use first data row
        header_row = table.headers[0] if table.headers else table.rows[0]
        data_rows = table.rows if table.headers else table.rows[1:]

        # Build header line
        header_cells = [self._escape_markdown(cell.text) for cell in header_row.cells]
        lines.append("| " + " | ".join(header_cells) + " |")

        # Build delimiter line
        delimiters = []
        for cell in header_row.cells:
            width = len(cell.text)
            if cell.col_span > 1:
                width = min(width, 10)  # Cap width for spanning cells
            delimiters.append("-" * max(3, width))
        lines.append("| " + " | ".join(delimiters) + " |")

        # Build data rows
        for row in data_rows:
            row_cells = []
            col_index = 0
            for cell in row.cells:
                cell_text = self._escape_markdown(cell.text)
                # Handle colspan by repeating cells
                repeat = max(1, cell.col_span)
                for _ in range(repeat):
                    row_cells.append(cell_text)
                    col_index += 1
            lines.append("| " + " | ".join(row_cells) + " |")

        return "\n".join(lines)

    def _find_matching_table_close(self, html: str, table_start: int) -> int | None:
        """Find the matching </table> tag for a <table> tag.

        Args:
            html: Full HTML content.
            table_start: Starting position of the <table> tag.

        Returns:
            Position of the matching </table> tag, or None if not found.
        """
        depth = 0
        # Start searching after the opening <table> tag we found
        open_match = self.TABLE_OPEN_RE.search(html, table_start)
        if not open_match:
            return None
        pos = open_match.end()

        while pos < len(html):
            # Look for next table open or close tag
            open_match = self.TABLE_OPEN_RE.search(html, pos)
            close_match = self.TABLE_CLOSE_RE.search(html, pos)

            if not close_match:
                return None  # No closing tag found

            if open_match and open_match.start() < close_match.start():
                depth += 1
                pos = open_match.end()
            else:
                if depth == 0:
                    return close_match.end()
                depth -= 1
                pos = close_match.end()

        return None

    def _parse_table(self, table_html: str) -> HTMLTable:
        """Parse a single HTML table string into an HTMLTable object.

        Args:
            table_html: Raw HTML content of a single <table> element.

        Returns:
            Parsed HTMLTable object.
        """
        # Extract caption
        caption_match = self.CAPTION_RE.search(table_html)
        caption = ""
        if caption_match:
            caption = self._strip_tags(caption_match.group(1).strip())

        # Extract rows
        header_rows: list[HTMLTableRow] = []
        data_rows: list[HTMLTableRow] = []

        for tr_match in self.TR_OPEN_RE.finditer(table_html):
            tr_start = tr_match.start()
            tr_end = self._find_matching_tr_close(table_html, tr_start)
            if tr_end is None:
                continue

            tr_html = table_html[tr_start:tr_end]
            row = self._parse_row(tr_html)

            if row.is_header:
                header_rows.append(row)
            else:
                data_rows.append(row)

        return HTMLTable(
            headers=tuple(header_rows),
            rows=tuple(data_rows),
            raw_html=table_html,
            caption=caption,
        )

    def _find_matching_tr_close(self, html: str, tr_start: int) -> int | None:
        """Find the matching </tr> tag for a <tr> tag.

        Args:
            html: Table HTML content.
            tr_start: Starting position of the <tr> tag.

        Returns:
            Position of the matching </tr> tag, or None if not found.
        """
        close_match = self.TR_CLOSE_RE.search(html, tr_start)
        if close_match:
            return close_match.end()
        return None

    def _parse_row(self, tr_html: str) -> HTMLTableRow:
        """Parse a single <tr> element into an HTMLTableRow.

        Args:
            tr_html: Raw HTML content of a single <tr> element.

        Returns:
            Parsed HTMLTableRow object.
        """
        # Try to parse as header row first (th elements)
        th_matches = list(self.TH_RE.finditer(tr_html))
        is_header = len(th_matches) > 0

        if is_header:
            cells = []
            for match in th_matches:
                cell_html = match.group(0)
                cell_content = match.group(1)
                text = self._strip_tags(cell_content.strip())
                cells.append(
                    HTMLTableCell(
                        text=text,
                        raw_html=cell_html,
                        is_header=True,
                        row_span=self._extract_rowspan(cell_html),
                        col_span=self._extract_colspan(cell_html),
                    )
                )
            return HTMLTableRow(
                cells=tuple(cells),
                raw_html=tr_html,
                is_header=True,
            )

        # Parse as data row (td elements)
        td_matches = list(self.TD_RE.finditer(tr_html))
        cells = []
        for match in td_matches:
            cell_html = match.group(0)
            cell_content = match.group(1)
            text = self._strip_tags(cell_content.strip())
            cells.append(
                HTMLTableCell(
                    text=text,
                    raw_html=cell_html,
                    is_header=False,
                    row_span=self._extract_rowspan(cell_html),
                    col_span=self._extract_colspan(cell_html),
                )
            )

        return HTMLTableRow(
            cells=tuple(cells),
            raw_html=tr_html,
            is_header=False,
        )

    def _strip_tags(self, text: str) -> str:
        """Remove HTML tags from text, preserving basic structure.

        Args:
            text: Text that may contain HTML tags.

        Returns:
            Text with HTML tags removed.
        """
        # Replace <br> and similar with newline
        text = re.sub(r"<br\s*/?>", "\n", text, flags=re.IGNORECASE)
        # Remove all other tags (but preserve newlines from <br>)
        text = self._strip_tags_re.sub(" ", text)
        # Clean up whitespace but preserve newlines
        lines = text.split("\n")
        cleaned_lines = [" ".join(line.split()) for line in lines]
        return "\n".join(cleaned_lines)

    def _extract_rowspan(self, tag_html: str) -> int:
        """Extract rowspan value from a td/th tag.

        Args:
            tag_html: Raw HTML tag content.

        Returns:
            Rowspan value (default 1).
        """
        match = self.ROWSPAN_RE.search(tag_html)
        if match:
            try:
                return int(match.group(1))
            except (ValueError, IndexError):
                pass
        return 1

    def _extract_colspan(self, tag_html: str) -> int:
        """Extract colspan value from a td/th tag.

        Args:
            tag_html: Raw HTML tag content.

        Returns:
            Colspan value (default 1).
        """
        match = self.COLSPAN_RE.search(tag_html)
        if match:
            try:
                return int(match.group(1))
            except (ValueError, IndexError):
                pass
        return 1

    def _escape_markdown(self, text: str) -> str:
        """Escape special markdown characters in table cell text.

        Args:
            text: Plain text content.

        Returns:
            Text with markdown special characters escaped.
        """
        # Escape pipe characters which are significant in markdown tables
        text = text.replace("|", "\\|")
        # Clean up whitespace
        return text.strip()
