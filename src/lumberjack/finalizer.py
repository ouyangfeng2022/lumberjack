from __future__ import annotations

from collections.abc import Iterable

from ._internal.rendering import RENDER_SEPARATOR, join_rendered_blocks
from .models import (
    Chunk,
    ChunkDraft,
    DocTree,
    Entry,
    HeadingPath,
    common_heading_path,
    render_heading_path,
)
from .normalizer import TextNormalizer
from .protocols import (
    TextNormalizerProtocol,
    TextTransformerProtocol,
    TokenizerProtocol,
)
from .transformer import TextTransformer


def render_draft_body(entries: list[Entry], external_headings: HeadingPath) -> str:
    """Render a draft body while keeping its external headings as metadata."""
    parts: list[str] = []
    previous_headings = external_headings
    for entry in entries:
        shared = common_heading_path((previous_headings, entry.headings))
        if len(shared) < len(external_headings):
            shared = external_headings
        relative_headings = entry.headings[len(shared) :]
        entry_parts: list[str] = []
        if relative_headings:
            entry_parts.append(render_heading_path(relative_headings))
        if entry.body:
            entry_parts.append(entry.body)
        rendered = join_rendered_blocks(entry_parts)
        if rendered:
            parts.append(rendered)
        previous_headings = entry.headings
    return join_rendered_blocks(parts)


class ChunkFinalizer:
    """Normalize, transform, measure, and finish drafts into chunks."""

    def __init__(
        self,
        tokenizer: TokenizerProtocol,
        *,
        normalizer: TextNormalizerProtocol | None = None,
        transformer: TextTransformerProtocol | None = None,
        skip_empty_sections: bool = True,
    ) -> None:
        self.tokenizer = tokenizer
        self.normalizer = normalizer or TextNormalizer()
        self.transformer = transformer or TextTransformer()
        self.skip_empty_sections = skip_empty_sections

    def finalize(self, document: DocTree, drafts: Iterable[ChunkDraft]) -> list[Chunk]:
        finished: list[Chunk] = []
        for draft in drafts:
            body = render_draft_body(draft.entries, draft.headings)
            body = self.transformer.transform(self.normalizer.normalize(body))
            if self.skip_empty_sections and not body.strip():
                continue

            heading_text = render_heading_path(draft.headings)
            headings_token_count = self.tokenizer.count(heading_text, cache=True)
            body_token_count = self.tokenizer.count(body, cache=True)
            token_count = (
                headings_token_count
                + self.tokenizer.count(RENDER_SEPARATOR, cache=True)
                + body_token_count
            )
            ancestor_headings = (
                draft.headings[:-1] if draft.own_heading is not None else draft.headings
            )
            finished.append(
                Chunk(
                    chunk_id=f"chunk-{len(finished) + 1:04d}",
                    chunk_type=draft.chunk_type,
                    body=body,
                    token_count=token_count,
                    estimated_token_count=(
                        token_count
                        if draft.counting_mode == "exact"
                        else draft.token_count
                    ),
                    headings_token_count=headings_token_count,
                    body_token_count=body_token_count,
                    ancestor_headings=ancestor_headings,
                    own_heading=draft.own_heading,
                    section_level=max(
                        (
                            level
                            for entry in draft.entries
                            for level, _ in entry.headings
                        ),
                        default=0,
                    ),
                    document_title=document.title,
                    document_path=document.source_path,
                    start_line=min(
                        (
                            entry.start_line
                            for entry in draft.entries
                            if entry.start_line is not None
                        ),
                        default=None,
                    ),
                    end_line=max(
                        (
                            entry.end_line
                            for entry in draft.entries
                            if entry.end_line is not None
                        ),
                        default=None,
                    ),
                )
            )
        return finished


__all__ = ["ChunkFinalizer", "render_draft_body"]
