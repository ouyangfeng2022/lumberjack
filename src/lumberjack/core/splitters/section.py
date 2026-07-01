from __future__ import annotations

from ..models import ChunkDraft, Entry, HeadingPath, MeasuredSection, SectionNode
from ..utils import join_markdown
from .base import BaseSplitter


class SectionSplitter(BaseSplitter):
    """Split a document into non-overlapping chunks by heading section.

    Each heading-defined section becomes its own chunk.  Oversized section
    bodies are further split by token budget respecting ``block_options``
    (standalone isolation, splittable kinds, per-block budgets).

    Counting path: when ``tokenizer.is_exact`` the splitter fully recounts
    rendered text for budget decisions (no pre-measure); otherwise it uses
    the additive incremental estimate path.

    Budget semantics with ``render_headings=False``: because every entry in
    a SectionSplitter chunk shares the chunk's common heading path (there are
    no internal relative headings), the heading breadcrumb contributes zero
    tokens to the rendered body.  This class therefore excludes heading
    tokens from the split budget when headings are not rendered, so
    ``max_tokens`` faithfully bounds the rendered ``Chunk.body``.
    """

    def _heading_budget_token_count(self, path: HeadingPath) -> int:
        """Exclude heading tokens from the budget when they are not rendered.

        SectionSplitter chunks never contain internal relative headings, so
        the common heading path is the only heading context and it is omitted
        from ``Chunk.body`` when ``render_headings=False``.
        """
        if not self.options.render_headings:
            return 0
        return self._heading_path_token_count(path)

    # ------------------------------------------------------------------
    # Incremental path (tiktoken / transformers)
    # ------------------------------------------------------------------

    def _split_section(
        self,
        section: MeasuredSection,
    ) -> list[ChunkDraft]:
        """Return one direct-body draft per section, then recurse into children."""
        chunks: list[ChunkDraft] = []
        node = section.node

        if node.blocks or node.level > 0:
            body_has_standalone = any(
                b.kind in self.options.standalone_kinds for b in node.blocks
            )
            if (
                body_has_standalone
                or section.counts.body > self.options.ideal_max_tokens
            ):
                body_chunks = self._split_section_body(section)
                chunks.extend(
                    self._merge_small_chunks(body_chunks, parent_headings=node.path)
                )
            else:
                entry = self._entry_from_blocks(
                    node.path,
                    node.blocks,
                    body_token_count=section.counts.body,
                )
                headings_token_count = self._heading_budget_token_count(node.path)
                chunks.append(
                    ChunkDraft(
                        entries=[entry],
                        headings=node.path,
                        headings_token_count=headings_token_count,
                        body_token_count=section.counts.body,
                        token_count=headings_token_count + section.counts.body,
                    )
                )

        for child in section.children:
            chunks.extend(self._split_section(child))

        return chunks

    # ------------------------------------------------------------------
    # Exact path (approx) — no pre-measure
    # ------------------------------------------------------------------

    def _split_section_exact(self, section: SectionNode) -> list[ChunkDraft]:
        """Return one direct-body draft per section, then recurse into children."""
        chunks: list[ChunkDraft] = []
        standalone_kinds = self.options.standalone_kinds

        if section.blocks or section.level > 0:
            body_has_standalone = any(
                b.kind in standalone_kinds for b in section.blocks
            )
            body = join_markdown([b.text for b in section.blocks])
            body_tokens = self.tokenizer.count(body, cache=True)
            # SectionSplitter emits one chunk per section, so the heading
            # breadcrumb is the only heading context and is constant for this
            # draft — comparing body tokens against the body-only budget is
            # equivalent to comparing the full rendered footprint against
            # ideal_max_tokens.
            body_budget = self._exact_body_budget(section.path)
            should_split_body = body_has_standalone or body_tokens > body_budget
            if should_split_body:
                body_chunks = self._split_section_body_exact(section)
                chunks.extend(
                    self._merge_small_chunks(body_chunks, parent_headings=section.path)
                )
            else:
                entry = Entry(
                    headings=section.path,
                    body=body,
                    start_line=self._min_start_lines(section.blocks),
                    end_line=self._max_end_lines(section.blocks),
                    body_token_count=body_tokens,
                )
                headings_token_count = self._heading_budget_token_count(section.path)
                chunks.append(
                    ChunkDraft(
                        entries=[entry],
                        headings=section.path,
                        headings_token_count=headings_token_count,
                        body_token_count=body_tokens,
                        token_count=headings_token_count + body_tokens,
                    )
                )

        for child in section.children:
            chunks.extend(self._split_section_exact(child))

        return chunks


__all__ = ["SectionSplitter"]
