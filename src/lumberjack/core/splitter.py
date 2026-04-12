from __future__ import annotations

import re
from dataclasses import dataclass

from ..base.interfaces import SplitterProtocol, TokenizerProtocol
from ..models import Chunk, DocumentAST, HeadingPath, MarkdownBlock, SectionNode, SplitOptions
from ..utils import join_markdown, render_heading_path
from .tokenizers import SimpleCharTokenizer

SENTENCE_BREAK_RE = re.compile(r"(?<=[.!?])\s+")


@dataclass(slots=True)
class _Fragment:
    headings: HeadingPath
    prefix: str
    blocks: list[MarkdownBlock]
    section_level: int

    def render(self) -> str:
        parts = [self.prefix] if self.prefix else []
        parts.extend(block.text for block in self.blocks)
        return join_markdown(parts)


class MarkdownSplitter(SplitterProtocol):
    def __init__(self, tokenizer: TokenizerProtocol | None = None):
        self.tokenizer = tokenizer or SimpleCharTokenizer()

    def split(self, document: DocumentAST, options: SplitOptions) -> list[Chunk]:
        self._validate_options(options)
        fragments = self._build_fragments(document.root, retain_headings=options.retain_headings)
        chunks = self._merge_fragments(fragments, options)
        if options.merge_small_chunks:
            chunks = self._merge_small_chunks(chunks, options)
        return chunks

    def _validate_options(self, options: SplitOptions) -> None:
        if options.max_tokens <= 0:
            raise ValueError("max_tokens must be greater than 0")
        if options.min_tokens < 0:
            raise ValueError("min_tokens must be non-negative")
        if options.min_tokens >= options.max_tokens:
            raise ValueError("min_tokens must be smaller than max_tokens")

    def _build_fragments(self, section: SectionNode, *, retain_headings: bool) -> list[_Fragment]:
        fragments: list[_Fragment] = []

        if section.blocks:
            prefix = (
                render_heading_path(section.path) if retain_headings and section.level > 0 else ""
            )
            fragments.append(
                _Fragment(
                    headings=section.path,
                    prefix=prefix,
                    blocks=section.blocks.copy(),
                    section_level=section.level,
                )
            )
        elif not section.children and section.level > 0:
            prefix = render_heading_path(section.path) if retain_headings else ""
            fragments.append(
                _Fragment(
                    headings=section.path,
                    prefix=prefix,
                    blocks=[],
                    section_level=section.level,
                )
            )

        for child in section.children:
            fragments.extend(self._build_fragments(child, retain_headings=retain_headings))

        return fragments

    def _merge_fragments(self, fragments: list[_Fragment], options: SplitOptions) -> list[Chunk]:
        chunks: list[Chunk] = []
        current_parts: list[str] = []
        current_tokens = 0
        current_headings: HeadingPath = ()
        current_level = 0

        for fragment in fragments:
            rendered = fragment.render()
            token_count = self.tokenizer.count(rendered)
            if token_count > options.max_tokens:
                if current_parts:
                    chunks.append(
                        Chunk(
                            text=join_markdown(current_parts),
                            token_count=current_tokens,
                            headings=current_headings,
                            section_level=current_level,
                        )
                    )
                    current_parts = []
                    current_tokens = 0
                    current_headings = ()
                    current_level = 0

                chunks.extend(self._split_fragment(fragment, options.max_tokens))
                continue

            if current_parts and current_tokens + token_count > options.max_tokens:
                chunks.append(
                    Chunk(
                        text=join_markdown(current_parts),
                        token_count=current_tokens,
                        headings=current_headings,
                        section_level=current_level,
                    )
                )
                current_parts = []
                current_tokens = 0
                current_headings = ()
                current_level = 0

            current_parts.append(rendered)
            current_tokens += token_count
            if not current_headings:
                current_headings = fragment.headings
                current_level = fragment.section_level

        if current_parts:
            chunks.append(
                Chunk(
                    text=join_markdown(current_parts),
                    token_count=current_tokens,
                    headings=current_headings,
                    section_level=current_level,
                )
            )

        return chunks

    def _split_fragment(self, fragment: _Fragment, max_tokens: int) -> list[Chunk]:
        prefix_tokens = self.tokenizer.count(fragment.prefix) if fragment.prefix else 0
        if prefix_tokens >= max_tokens:
            rendered = fragment.render()
            return [
                Chunk(
                    text=rendered,
                    token_count=self.tokenizer.count(rendered),
                    headings=fragment.headings,
                    section_level=fragment.section_level,
                )
            ]

        chunks: list[Chunk] = []
        current_parts = [fragment.prefix] if fragment.prefix else []
        current_tokens = prefix_tokens

        if not fragment.blocks:
            rendered = fragment.render()
            return [
                Chunk(
                    text=rendered,
                    token_count=self.tokenizer.count(rendered),
                    headings=fragment.headings,
                    section_level=fragment.section_level,
                )
            ]

        for block in fragment.blocks:
            block_tokens = self.tokenizer.count(block.text)
            budget = max_tokens - prefix_tokens

            if (
                current_parts
                and current_tokens > prefix_tokens
                and current_tokens + block_tokens > max_tokens
            ):
                chunks.append(
                    Chunk(
                        text=join_markdown(current_parts),
                        token_count=current_tokens,
                        headings=fragment.headings,
                        section_level=fragment.section_level,
                    )
                )
                current_parts = [fragment.prefix] if fragment.prefix else []
                current_tokens = prefix_tokens

            if prefix_tokens + block_tokens <= max_tokens:
                current_parts.append(block.text)
                current_tokens += block_tokens
                continue

            if block.kind == "code_fence":
                oversized_parts = [fragment.prefix, block.text] if fragment.prefix else [block.text]
                chunks.append(
                    Chunk(
                        text=join_markdown(oversized_parts),
                        token_count=prefix_tokens + block_tokens,
                        headings=fragment.headings,
                        section_level=fragment.section_level,
                    )
                )
                current_parts = [fragment.prefix] if fragment.prefix else []
                current_tokens = prefix_tokens
                continue

            for piece in self._split_text(block.text, max_tokens=budget):
                piece_tokens = self.tokenizer.count(piece)
                chunks.append(
                    Chunk(
                        text=join_markdown([fragment.prefix, piece]) if fragment.prefix else piece,
                        token_count=prefix_tokens + piece_tokens,
                        headings=fragment.headings,
                        section_level=fragment.section_level,
                    )
                )

        minimum_parts = 1 if fragment.prefix else 0
        if current_parts and len(current_parts) > minimum_parts:
            rendered = join_markdown(current_parts)
            if rendered:
                chunks.append(
                    Chunk(
                        text=rendered,
                        token_count=current_tokens,
                        headings=fragment.headings,
                        section_level=fragment.section_level,
                    )
                )

        return chunks

    def _split_text(self, text: str, *, max_tokens: int) -> list[str]:
        if self.tokenizer.count(text) <= max_tokens:
            return [text]

        for separator in ("\n\n", "\n"):
            parts = [part.strip() for part in text.split(separator) if part.strip()]
            if len(parts) > 1:
                packed = self._pack_parts(parts, max_tokens, separator=separator)
                if all(self.tokenizer.count(part) <= max_tokens for part in packed):
                    return packed

        sentence_parts = [part.strip() for part in SENTENCE_BREAK_RE.split(text) if part.strip()]
        if len(sentence_parts) > 1:
            packed = self._pack_parts(sentence_parts, max_tokens, separator=" ")
            if all(self.tokenizer.count(part) <= max_tokens for part in packed):
                return packed

        word_parts = [part for part in text.split(" ") if part]
        if len(word_parts) > 1:
            packed = self._pack_parts(word_parts, max_tokens, separator=" ")
            if all(self.tokenizer.count(part) <= max_tokens for part in packed):
                return packed

        return self._hard_split(text, max_tokens)

    def _pack_parts(self, parts: list[str], max_tokens: int, *, separator: str) -> list[str]:
        packed: list[str] = []
        current = ""
        for part in parts:
            candidate = part if not current else f"{current}{separator}{part}"
            if current and self.tokenizer.count(candidate) > max_tokens:
                packed.append(current)
                current = part
            else:
                current = candidate
        if current:
            packed.append(current)
        return packed

    def _hard_split(self, text: str, max_tokens: int) -> list[str]:
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
        return [part.strip() for part in parts if part.strip()]

    def _merge_small_chunks(self, chunks: list[Chunk], options: SplitOptions) -> list[Chunk]:
        if not chunks:
            return chunks

        merged: list[Chunk] = [chunks[0]]
        for chunk in chunks[1:]:
            previous = merged[-1]
            if (
                chunk.token_count < options.min_tokens
                and previous.token_count + chunk.token_count <= options.max_tokens
            ):
                merged[-1] = Chunk(
                    text=join_markdown([previous.text, chunk.text]),
                    token_count=previous.token_count + chunk.token_count,
                    headings=previous.headings or chunk.headings,
                    section_level=previous.section_level or chunk.section_level,
                )
            else:
                merged.append(chunk)
        return merged
