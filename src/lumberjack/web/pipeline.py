"""Web-specific parser and splitter that extend the core pipeline for visualization."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import TYPE_CHECKING, Any

from ..core.parser import MarkdownItParser
from ..core.splitter import MarkdownSplitter, _ChunkDraft, _Entry

if TYPE_CHECKING:
    from ..models import Chunk, DocumentAST


@dataclass(slots=True)
class PipelineSteps:
    """Intermediate pipeline data for visualization."""

    entries: list[_Entry]
    drafts_after_merge: list[_ChunkDraft]
    chunks: list[Chunk]


class WebParser(MarkdownItParser):
    """Extended parser that also exposes the raw token stream for web visualization."""

    def parse_tokens(self, text: str) -> list[dict[str, object]]:
        """Return the raw markdown-it token stream as serializable dicts."""
        env: dict[str, Any] = {}
        tokens = self._parser.parse(text, env)
        return [asdict(t) for t in tokens]


class WebSplitter(MarkdownSplitter):
    """Extended splitter that captures intermediate pipeline stages for web visualization."""

    def split_with_steps(self, document: DocumentAST) -> PipelineSteps:
        """Split and return intermediate pipeline data for visualization."""
        self._validate_options()
        front_matter_block = self._extract_front_matter(document.root)
        self._cache_block_token_count.clear()
        self._cache_title_token_count.clear()
        measured_root = self._measure_section(document.root)
        entries = self._entries_from_section(measured_root)
        drafts_before = self._split_section(measured_root)
        drafts_after = (
            self._merge_small_chunks(drafts_before)
            if self.options.merge_small_chunks
            else drafts_before
        )
        chunks = self._finalize_chunks(drafts_after, document)
        if front_matter_block is not None:
            chunks.insert(0, self._make_front_matter_chunk(front_matter_block, document))
        return PipelineSteps(
            entries=entries,
            drafts_after_merge=drafts_after,
            chunks=chunks,
        )
