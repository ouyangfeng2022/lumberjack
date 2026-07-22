"""Block splitting and block-config parsing helpers.

- :class:`BlockSplitter` splits oversized text/code/table/list blocks into
  token-bounded pieces.
- :func:`parse_block_config_entry` parses ``KIND[:isolated][:nosplit][:TOKENS]``
  strings into ``(kind, BaseParams)`` pairs for the CLI.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

from .models import BaseParams, BlockKindRegistry, SplitOptions, TableBlockParams
from .parser.html.table_parser import HTMLTableParser, HTMLTableRow

if TYPE_CHECKING:
    from .models import DocumentBlock
    from .protocols import TokenizerProtocol

SENTENCE_BREAK_RE = re.compile(r"(?<=[.!?\u3002\uff01\uff1f])\s+")
PROTECTED_SPAN_RE = re.compile(r"<https?://[^\s>]+>|https?://[^\s)>\]]+")
TABLE_DELIMITER_CELL_RE = re.compile(r":?-+(:?-+)*:?")


class BlockSplitter:
    """Splits oversized text blocks into token-bounded pieces."""

    def __init__(
        self,
        tokenizer: TokenizerProtocol,
        options: SplitOptions | None = None,
    ) -> None:
        self.tokenizer = tokenizer
        self.options = options or SplitOptions()
        self._html_table_parser = HTMLTableParser()

    def split_oversized_block(
        self,
        block: DocumentBlock,
        *,
        default_budget: int,
    ) -> list[tuple[str, int]] | None:
        config = self._block_config(block.kind)
        if config is None or not config.split:
            return None

        budget = self._block_budget(block.kind, default_budget)

        if block.kind in {"code_block", "code_fence"}:
            return self.split_code_block(block, max_tokens=budget)

        if block.kind == "list" and block.children:
            return self.split_list_block(block, max_tokens=budget)

        if block.kind == "table":
            return self.split_table_block(block, default_budget=default_budget)

        if block.kind == "html_table":
            return self.split_html_table_block(
                block,
                default_budget=default_budget,
            )

        return self.split_text(block.text, max_tokens=budget)

    def _block_config(self, kind: str) -> BaseParams | None:
        return self.options.block_options.get(kind.lower())

    def _block_budget(self, kind: str, default_budget: int | None = None) -> int:
        config = self._block_config(kind)
        if config and config.max_tokens:
            return config.max_tokens
        if default_budget is not None:
            return default_budget
        return self.options.max_tokens

    def _repeat_header(self, kind: str) -> bool:
        config = self._block_config(kind)
        return not isinstance(config, TableBlockParams) or config.repeat_header

    def split_code_block(
        self,
        block: DocumentBlock,
        *,
        max_tokens: int,
    ) -> list[tuple[str, int]]:
        info = str(block.attrs.get("info") or block.attrs.get("language") or "").strip()
        literal = str(block.attrs.get("literal") or "")
        open_fence = f"```{info}".rstrip()
        close_fence = "```"
        empty_render = f"{open_fence}\n{close_fence}"
        wrapper_tokens = self.tokenizer.count(empty_render, cache=True)
        if wrapper_tokens >= max_tokens:
            return [(block.text, self.tokenizer.count(block.text, cache=True))]

        code_budget = max_tokens - wrapper_tokens
        pieces = self.split_text(literal, max_tokens=code_budget)
        result: list[tuple[str, int]] = []
        for piece, _piece_tokens in pieces:
            wrapped = f"{open_fence}\n{piece}\n{close_fence}"
            # Fences add tokens beyond the literal, so recount the wrapped text.
            result.append((wrapped, self.tokenizer.count(wrapped, cache=True)))
        return result

    def split_table_block(
        self,
        block: DocumentBlock,
        *,
        default_budget: int | None = None,
    ) -> list[tuple[str, int]]:
        # Handle markdown table
        lines = [line.rstrip() for line in block.text.splitlines() if line.strip()]
        max_tokens = self._block_budget(block.kind, default_budget)
        repeat_header = self._repeat_header(block.kind)
        if len(lines) < 3 or not self.is_table_delimiter_row(lines[1]):
            return self.split_text(block.text, max_tokens=max_tokens)

        def emit_piece(piece_header: list[str], rows: list[str]) -> tuple[str, int]:
            piece = self.render_table_piece(piece_header, rows)
            return (piece, self.tokenizer.count(piece, cache=True))

        header = lines[:2]
        rows = lines[2:]
        pieces: list[tuple[str, int]] = []
        current_rows: list[str] = []

        for row in rows:
            candidate_rows = [*current_rows, row]
            candidate_header = header if repeat_header or not pieces else []
            candidate = self.render_table_piece(candidate_header, candidate_rows)
            candidate_tokens = self.tokenizer.count(candidate, cache=True)
            if current_rows and candidate_tokens > max_tokens:
                piece_header = header if repeat_header or not pieces else []
                pieces.append(emit_piece(piece_header, current_rows))
                current_rows = [row]
                single_header = header if repeat_header or not pieces else []
                single_row = self.render_table_piece(single_header, current_rows)
                single_tokens = self.tokenizer.count(single_row, cache=True)
                if single_tokens > max_tokens:
                    pieces.append((single_row, single_tokens))
                    current_rows = []
                continue

            if not current_rows and candidate_tokens > max_tokens:
                pieces.append((candidate, candidate_tokens))
                continue

            current_rows = candidate_rows

        if current_rows:
            piece_header = header if repeat_header or not pieces else []
            pieces.append(emit_piece(piece_header, current_rows))

        return pieces or [(block.text, self.tokenizer.count(block.text, cache=True))]

    def is_table_delimiter_row(self, line: str) -> bool:
        cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
        return bool(cells) and all(
            cell and TABLE_DELIMITER_CELL_RE.fullmatch(cell) for cell in cells
        )

    def render_table_piece(self, header: list[str], rows: list[str]) -> str:
        return "\n".join([*header, *rows])

    def split_html_table_block(
        self,
        block: DocumentBlock,
        *,
        default_budget: int | None = None,
    ) -> list[tuple[str, int]]:
        """Split an HTML table while preserving its original HTML format.

        This method extracts HTML tables and splits them by rows while keeping
        the HTML structure intact, without converting to markdown format.
        """
        max_tokens = self._block_budget(block.kind, default_budget)
        repeat_header = self._repeat_header(block.kind)
        tables = self._html_table_parser.extract_tables(block.text)
        if not tables:
            return [(block.text, self.tokenizer.count(block.text, cache=True))]

        def emit(html: str) -> tuple[str, int]:
            return (html, self.tokenizer.count(html, cache=True))

        pieces: list[tuple[str, int]] = []
        for html_table in tables:
            # Get the raw HTML content
            table_html = html_table.raw_html

            # Extract the opening <table> tag with all attributes
            table_open_tag = ""
            table_match = re.search(r"<table\b[^>]*>", table_html, re.IGNORECASE)
            if table_match:
                table_open_tag = table_match.group(0)

            # Extract caption if present
            caption_html = ""
            if html_table.caption:
                caption_match = self._html_table_parser.CAPTION_RE.search(table_html)
                if caption_match:
                    caption_html = caption_match.group(0)

            # Split by rows while preserving HTML structure
            header_rows = list(html_table.headers)
            data_rows = list(html_table.rows)

            if not data_rows:
                pieces.append(emit(table_html))
                continue

            # Group rows by token budget
            current_rows: list[HTMLTableRow] = []
            pieces_count = 0

            for row in data_rows:
                test_rows = [*current_rows, row]
                # Build test HTML to check token count
                candidate_headers = (
                    header_rows if repeat_header or pieces_count == 0 else []
                )
                test_html = self._build_html_table_piece(
                    table_open_tag, caption_html, candidate_headers, test_rows
                )
                test_tokens = self.tokenizer.count(test_html, cache=True)

                if current_rows and test_tokens > max_tokens:
                    # Emit current group. ``piece_html`` differs from
                    # ``test_html`` (it drops the candidate row), so it needs
                    # its own count — but its headers share the same
                    # ``pieces_count == 0`` decision as ``candidate_headers``.
                    piece_headers = (
                        header_rows if repeat_header or pieces_count == 0 else []
                    )
                    piece_html = self._build_html_table_piece(
                        table_open_tag, caption_html, piece_headers, current_rows
                    )
                    pieces.append(emit(piece_html))
                    current_rows = [row]
                    pieces_count += 1
                elif not current_rows and test_tokens > max_tokens:
                    # Single row exceeds budget, emit ``test_html`` as is —
                    # reuse the count we just computed for the budget check.
                    pieces.append((test_html, test_tokens))
                    current_rows = []
                    pieces_count += 1
                else:
                    current_rows.append(row)

            # Don't forget remaining rows
            if current_rows:
                piece_headers = (
                    header_rows if repeat_header or pieces_count == 0 else []
                )
                piece_html = self._build_html_table_piece(
                    table_open_tag, caption_html, piece_headers, current_rows
                )
                pieces.append(emit(piece_html))
                pieces_count += 1

        return (
            pieces
            if pieces
            else [(block.text, self.tokenizer.count(block.text, cache=True))]
        )

    def _build_html_table_piece(
        self,
        table_open_tag: str,
        caption_html: str,
        header_rows: list[HTMLTableRow],
        data_rows: list[HTMLTableRow],
    ) -> str:
        """Build a complete HTML table piece from components.

        Args:
            table_open_tag: Complete opening <table> tag with attributes.
            caption_html: Raw HTML caption string.
            header_rows: List of header row objects.
            data_rows: List of data row objects to include.

        Returns:
            Complete HTML table string.
        """
        lines: list[str] = [table_open_tag if table_open_tag else "<table>"]

        # Add caption
        if caption_html:
            lines.append(caption_html)

        # Add header rows
        for header_row in header_rows:
            lines.append(header_row.raw_html)

        # Add data rows
        for data_row in data_rows:
            lines.append(data_row.raw_html)

        lines.append("</table>")
        return "\n".join(lines)

    def split_list_block(
        self,
        block: DocumentBlock,
        *,
        max_tokens: int,
    ) -> list[tuple[str, int]]:
        items = [child.text for child in block.children if child.text]
        if len(items) <= 1:
            return self.split_text(
                block.text,
                max_tokens=max_tokens,
            )

        packed = self.pack_parts(
            items,
            max_tokens,
            separator="\n",
        )
        if all(tokens <= max_tokens for _, tokens in packed):
            return packed

        pieces: list[tuple[str, int]] = []
        for item in items:
            item_tokens = self.tokenizer.count(item, cache=True)
            if item_tokens <= max_tokens:
                pieces.append((item, item_tokens))
                continue
            pieces.extend(
                self.split_text(
                    item,
                    max_tokens=max_tokens,
                )
            )
        return pieces

    def split_text(
        self,
        text: str,
        *,
        max_tokens: int,
    ) -> list[tuple[str, int]]:
        # TODO: optimize
        text_tokens = self.tokenizer.count(text, cache=True)
        if text_tokens <= max_tokens:
            return [(text, text_tokens)]

        if any(
            self.tokenizer.count(m.group(0)) > max_tokens
            for m in PROTECTED_SPAN_RE.finditer(text)
        ):
            return [(text, text_tokens)]

        for separator in ("\n\n", "\n"):
            parts = [part.strip() for part in text.split(separator) if part.strip()]
            if len(parts) > 1:
                packed = self.pack_parts(
                    parts,
                    max_tokens,
                    separator=separator,
                )
                if all(tokens <= max_tokens for _, tokens in packed):
                    return packed

        sentence_parts = [
            part.strip() for part in SENTENCE_BREAK_RE.split(text) if part.strip()
        ]
        if len(sentence_parts) > 1:
            packed = self.pack_parts(
                sentence_parts,
                max_tokens,
                separator=" ",
            )
            if all(tokens <= max_tokens for _, tokens in packed):
                return packed

        word_parts = [part for part in text.split(" ") if part]
        if len(word_parts) > 1:
            packed = self.pack_parts(
                word_parts,
                max_tokens,
                separator=" ",
            )
            if all(tokens <= max_tokens for _, tokens in packed):
                return packed

        return self.hard_split(text, max_tokens)

    def pack_parts(
        self,
        parts: list[str],
        max_tokens: int,
        *,
        separator: str,
    ) -> list[tuple[str, int]]:
        packed: list[tuple[str, int]] = []
        current_parts: list[str] = []
        current_joined = ""
        current_tokens = 0
        for part in parts:
            candidate_text = (
                current_joined + separator + part if current_joined else part
            )
            candidate_tokens = self.tokenizer.count(candidate_text, cache=True)
            if current_parts and candidate_tokens > max_tokens:
                packed.append((current_joined, current_tokens))
                current_parts = [part]
                current_joined = part
                current_tokens = self.tokenizer.count(part, cache=True)
            else:
                current_parts.append(part)
                current_joined = candidate_text
                current_tokens = candidate_tokens
        if current_parts:
            packed.append((current_joined, current_tokens))
        return packed

    def hard_split(
        self,
        text: str,
        max_tokens: int,
    ) -> list[tuple[str, int]]:
        parts: list[str] = []
        current = ""
        for character in text:
            candidate = f"{current}{character}"
            if current and self.tokenizer.count(candidate) > max_tokens:
                parts.append(current)
                current = character
            else:
                current = candidate
        if current:
            parts.append(current)
        result: list[tuple[str, int]] = []
        for part in parts:
            stripped = part.strip()
            if not stripped:
                continue
            result.append((stripped, self.tokenizer.count(stripped, cache=True)))
        return result


def parse_block_config_entry(
    entry: str, registry: BlockKindRegistry
) -> tuple[str, BaseParams]:
    """Parse a ``KIND[:isolated][:nosplit][:TOKENS]`` string into ``(kind, BaseParams)``.

    The colon-separated parts after the kind name are classified by content:

    - ``isolated`` → ``isolated=True``
    - ``nosplit`` → ``split=False``
    - positive integer → ``max_tokens``

    Raises :class:`ValueError` on unknown kind or bad tokens.
    """
    parts = entry.split(":")
    kind = parts[0].strip().lower()
    if not kind:
        raise ValueError(f"Empty block kind in: {entry!r}")
    registry.validate_kind(kind)

    isolated = False
    split = True
    max_tokens: int | None = None

    for part in parts[1:]:
        part = part.strip()
        if not part:
            continue
        lower = part.lower()
        if lower == "isolated":
            isolated = True
        elif lower == "nosplit":
            split = False
        else:
            try:
                tokens = int(part)
            except ValueError:
                raise ValueError(
                    f"Invalid spec in: {entry!r} "
                    f"(expected 'isolated', 'nosplit', or integer, got {part!r})"
                ) from None
            if tokens <= 0:
                raise ValueError(f"Token count must be positive in: {entry!r}")
            max_tokens = tokens

    params_cls = TableBlockParams if kind in {"table", "html_table"} else BaseParams
    return kind, params_cls(isolated=isolated, split=split, max_tokens=max_tokens)
