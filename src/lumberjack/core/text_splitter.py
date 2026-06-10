from __future__ import annotations

import re
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .models import MarkdownBlock
    from .protocols import TokenizerProtocol

SENTENCE_BREAK_RE = re.compile(r"(?<=[.!?\u3002\uFF01\uFF1F])\s+")
PROTECTED_SPAN_RE = re.compile(r"<https?://[^\s>]+>|https?://[^\s)>\]]+")
TABLE_DELIMITER_CELL_RE = re.compile(r":?-+(:?-+)*:?")


class TextSplitter:
    """Splits oversized text blocks into token-bounded pieces."""

    def __init__(self, tokenizer: TokenizerProtocol, overlap_tokens: int = 0):
        self.tokenizer = tokenizer
        self.overlap_tokens = overlap_tokens

    def split_oversized_block(
        self,
        block: MarkdownBlock,
        *,
        max_tokens: int,
        allowed_kinds: frozenset[str] | set[str],
    ) -> list[str] | None:
        if block.kind.lower() not in allowed_kinds:
            return None

        if block.kind in {"code_block", "code_fence"}:
            return self.split_code_block(block, max_tokens=max_tokens)

        if block.kind == "list" and block.children:
            return self.split_list_block(block, max_tokens=max_tokens)

        if block.kind == "table":
            return self.split_table_block(block, max_tokens=max_tokens)

        return self.split_text(block.text, max_tokens=max_tokens)

    def split_code_block(
        self,
        block: MarkdownBlock,
        *,
        max_tokens: int,
    ) -> list[str]:
        info = str(block.attrs.get("info") or block.attrs.get("language") or "").strip()
        literal = str(block.attrs.get("literal") or "")
        open_fence = f"```{info}".rstrip()
        close_fence = "```"
        empty_render = f"{open_fence}\n{close_fence}"
        wrapper_tokens = self.tokenizer.count(empty_render, cache=True)
        if wrapper_tokens >= max_tokens:
            return [block.text]

        code_budget = max_tokens - wrapper_tokens
        pieces = self.split_text(literal, max_tokens=code_budget)
        return [f"{open_fence}\n{piece}\n{close_fence}" for piece in pieces]

    def split_table_block(
        self,
        block: MarkdownBlock,
        *,
        max_tokens: int,
    ) -> list[str]:
        lines = [line.rstrip() for line in block.text.splitlines() if line.strip()]
        if len(lines) < 3 or not self.is_table_delimiter_row(lines[1]):
            return self.split_text(block.text, max_tokens=max_tokens)

        header = lines[:2]
        rows = lines[2:]
        pieces: list[str] = []
        current_rows: list[str] = []

        for row in rows:
            candidate_rows = [*current_rows, row]
            candidate = self.render_table_piece(header, candidate_rows)
            if current_rows and self.tokenizer.count(candidate) > max_tokens:
                pieces.append(self.render_table_piece(header, current_rows))
                current_rows = [row]
                single_row = self.render_table_piece(header, current_rows)
                if self.tokenizer.count(single_row) > max_tokens:
                    pieces.append(single_row)
                    current_rows = []
                continue

            if not current_rows and self.tokenizer.count(candidate) > max_tokens:
                pieces.append(candidate)
                continue

            current_rows = candidate_rows

        if current_rows:
            pieces.append(self.render_table_piece(header, current_rows))

        return pieces or [block.text]

    def is_table_delimiter_row(self, line: str) -> bool:
        cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
        return bool(cells) and all(
            cell and TABLE_DELIMITER_CELL_RE.fullmatch(cell) for cell in cells
        )

    def render_table_piece(self, header: list[str], rows: list[str]) -> str:
        return "\n".join([*header, *rows])

    def split_list_block(
        self,
        block: MarkdownBlock,
        *,
        max_tokens: int,
    ) -> list[str]:
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
            overlap_tokens=0,
        )
        if all(self.tokenizer.count(part) <= max_tokens for part in packed):
            return packed

        pieces: list[str] = []
        for item in items:
            if self.tokenizer.count(item) <= max_tokens:
                pieces.append(item)
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
    ) -> list[str]:
        overlap_tokens = self.overlap_tokens
        if self.tokenizer.count(text) <= max_tokens:
            return [text]

        if any(
            self.tokenizer.count(m.group(0)) > max_tokens
            for m in PROTECTED_SPAN_RE.finditer(text)
        ):
            return [text]

        for separator in ("\n\n", "\n"):
            parts = [part.strip() for part in text.split(separator) if part.strip()]
            if len(parts) > 1:
                packed = self.pack_parts(
                    parts,
                    max_tokens,
                    separator=separator,
                    overlap_tokens=overlap_tokens,
                )
                if all(self.tokenizer.count(part) <= max_tokens for part in packed):
                    return packed

        sentence_parts = [
            part.strip() for part in SENTENCE_BREAK_RE.split(text) if part.strip()
        ]
        if len(sentence_parts) > 1:
            packed = self.pack_parts(
                sentence_parts,
                max_tokens,
                separator=" ",
                overlap_tokens=overlap_tokens,
            )
            if all(self.tokenizer.count(part) <= max_tokens for part in packed):
                return packed

        word_parts = [part for part in text.split(" ") if part]
        if len(word_parts) > 1:
            packed = self.pack_parts(
                word_parts,
                max_tokens,
                separator=" ",
                overlap_tokens=overlap_tokens,
            )
            if all(self.tokenizer.count(part) <= max_tokens for part in packed):
                return packed

        return self.hard_split(text, max_tokens, overlap_tokens=overlap_tokens)

    def pack_parts(
        self,
        parts: list[str],
        max_tokens: int,
        *,
        separator: str,
        overlap_tokens: int,
    ) -> list[str]:
        packed: list[str] = []
        current_parts: list[str] = []
        current_joined = ""
        current_tokens = 0
        for part in parts:
            candidate_text = (
                current_joined + separator + part if current_joined else part
            )
            candidate_tokens = self.tokenizer.count(candidate_text)
            if current_parts and candidate_tokens > max_tokens:
                packed.append(current_joined)
                overlap_parts, _ = self.tail_parts_within_budget(
                    current_joined,
                    max_tokens=overlap_tokens,
                    separator=separator,
                )
                current_parts = [*overlap_parts, part]
                current_joined = separator.join(current_parts)
                current_tokens = self.tokenizer.count(current_joined)
                if current_tokens > max_tokens:
                    current_parts = [part]
                    current_joined = part
                    current_tokens = self.tokenizer.count(part)
            else:
                current_parts.append(part)
                current_joined = separator.join(current_parts)
                current_tokens = candidate_tokens
        if current_parts:
            packed.append(current_joined)
        return packed

    def hard_split(
        self,
        text: str,
        max_tokens: int,
        *,
        overlap_tokens: int,
    ) -> list[str]:
        parts: list[str] = []
        current = ""
        for character in text:
            candidate = f"{current}{character}"
            if current and self.tokenizer.count(candidate) > max_tokens:
                parts.append(current)
                overlap = self.suffix_within_budget(current, overlap_tokens)
                current = f"{overlap}{character}" if overlap else character
                if self.tokenizer.count(current) > max_tokens:
                    current = character
            else:
                current = candidate
        if current:
            parts.append(current)
        return [part.strip() for part in parts if part.strip()]

    def tail_parts_within_budget(
        self,
        current_joined: str,
        *,
        max_tokens: int,
        separator: str,
    ) -> tuple[list[str], int]:
        if max_tokens <= 0 or not current_joined:
            return ([], 0)
        parts = current_joined.split(separator)
        tail: list[str] = []
        for part in reversed(parts):
            candidate = separator.join([part, *tail]) if tail else part
            if self.tokenizer.count(candidate) > max_tokens:
                break
            tail = [part, *tail]
        tail_joined = separator.join(tail) if tail else ""
        return (tail, self.tokenizer.count(tail_joined))

    def suffix_within_budget(self, text: str, max_tokens: int) -> str:
        if max_tokens <= 0 or not text:
            return ""
        if self.tokenizer.count(text) <= max_tokens:
            return text

        for start in range(1, len(text)):
            suffix = text[start:]
            if any(
                m.start() < start < m.end() for m in PROTECTED_SPAN_RE.finditer(text)
            ):
                continue
            if self.tokenizer.count(suffix) <= max_tokens:
                return suffix
        return ""
