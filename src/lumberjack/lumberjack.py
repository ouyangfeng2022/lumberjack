from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path

from .finalizer import ChunkFinalizer
from .models import Chunk, InputFormat, Tree
from .normalizer import TextNormalizer
from .parser import AutoParser
from .protocols import (
    ParserProtocol,
    SplitterProtocol,
    TextNormalizerProtocol,
    TextTransformerProtocol,
    TokenizerProtocol,
)
from .splitter import SiblingSplitter
from .tokenizer import ApproxByteTokenizer
from .transformer import TextTransformer


class Lumberjack:
    """Orchestrate the complete tree-to-chunks lumber pipeline."""

    def __init__(
        self,
        *,
        tokenizer: TokenizerProtocol | None = None,
        parser: ParserProtocol | None = None,
        splitter: SplitterProtocol | None = None,
        normalizer: TextNormalizerProtocol | None = None,
        transformer: TextTransformerProtocol | None = None,
        max_tokens: int = 1200,
        skip_empty_sections: bool = True,
    ) -> None:
        if tokenizer is None and splitter is not None:
            tokenizer = splitter.tokenizer
        self.tokenizer = tokenizer or ApproxByteTokenizer()
        self.parser = parser or AutoParser()
        if splitter is not None and splitter.tokenizer is not self.tokenizer:
            raise ValueError(
                "splitter and finalize must share the same tokenizer instance"
            )
        self.splitter = splitter or SiblingSplitter(
            self.tokenizer,
            max_tokens=max_tokens,
            skip_empty_sections=skip_empty_sections,
        )
        self.finalizer = ChunkFinalizer(
            self.tokenizer,
            normalizer=normalizer or TextNormalizer(),
            transformer=transformer or TextTransformer(),
            skip_empty_sections=skip_empty_sections,
        )

    def saw(
        self,
        tree: Tree | str | bytes | Path,
        *,
        format: InputFormat = "auto",
        document_title: str | None = None,
        metadata_overrides: Mapping[str, object] | None = None,
        source_path: str | Path | None = None,
    ) -> list[Chunk]:
        """Parse, split, and finalize one raw document into final chunks."""
        if not isinstance(tree, Tree):
            tree = Tree(
                source=tree,
                format=format,
                document_title=document_title,
                metadata_overrides=dict(metadata_overrides or {}),
                source_path=source_path,
            )
        document = self.parser.parse(tree)
        drafts = self.splitter.split(document)
        return self.finalizer.finalize(document, drafts)


__all__ = ["Lumberjack"]
