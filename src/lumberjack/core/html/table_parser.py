"""HTML table extraction utility and parsed-table dataclasses."""

from __future__ import annotations

import re
from dataclasses import dataclass


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
