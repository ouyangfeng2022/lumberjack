# Lumberjack

Structure-aware Markdown, HTML, and DOCX lumbering for RAG preprocessing.

Lumberjack models document processing as a real lumber pipeline:

```text
Document -> Parser.parse() -> DocTree -> Splitter.split() -> ChunkDraft[]
     -> ChunkFinalizer.finalize() -> TextNormalizer -> TextTransformer -> Chunk[]
```

## Installation

```bash
pip install lumberjack

# Optional tokenizers, DOCX, and Web API support
pip install "lumberjack[tokenizers,docx,web]"
```

Python 3.10 or newer is required.

## Main API

The package root exposes `Lumberjack` and `Document`:

```python
from pathlib import Path

from lumberjack import Lumberjack, Document

jack = Lumberjack(max_tokens=1200)

# Raw values are wrapped into Document automatically.
chunks = jack.saw(Path("guide.md"))

# Document carries format, title, metadata, and source provenance explicitly.
chunks = jack.saw(
    Document(
        source=markdown_text,
        format="markdown",
        document_title="Guide",
        metadata_overrides={"tenant": "docs"},
        source_path="imports/guide.md",
    )
)
```

`Lumberjack()` defaults to `AutoParser`, `ApproxByteTokenizer`, incremental
`SiblingSplitter`, `TextNormalizer`, `TextTransformer`, and `ChunkFinalizer`. The same tokenizer instance is used for
split-budget estimates and final counts.

## Component pipeline

```python
from pathlib import Path

from lumberjack.block import BlockConfig, BlockKind, MarkdownTableConfig
from lumberjack.parser import AutoParser
from lumberjack.finalizer import ChunkFinalizer
from lumberjack.models import Document
from lumberjack.splitter import SiblingSplitter
from lumberjack.tokenizer import TiktokenTokenizer

tokenizer = TiktokenTokenizer(model="gpt-4o-mini")
parser = AutoParser()
splitter = SiblingSplitter(
    tokenizer,
    max_tokens=1200,
    block_options=[
        MarkdownTableConfig(isolated=True, max_tokens=500),
        BlockConfig(BlockKind.CODE_FENCE, split=False),
    ],
)
finalize = ChunkFinalizer(tokenizer)

document = parser.parse(Document(Path("guide.md")))
drafts = splitter.split(document)
chunks = finalize.finalize(document, drafts)
```

Public components:

- `lumberjack.parser`: `AutoParser`, `MarkdownParser`, `HTMLParser`, and
  `DocxParser` turn `Document` into the shared `DocTree` structure.
- `lumberjack.tokenizer`: `ApproxByteTokenizer`, `TiktokenTokenizer`, and
  `TransformersTokenizer` implement `encode()` and `count()`.
- `lumberjack.splitter`: incremental `SiblingSplitter`, `SubtreeSplitter`, and
  `SectionSplitter`, plus explicit `Exact*Splitter` implementations, produce `ChunkDraft`.
- `lumberjack.finalizer`: `ChunkFinalizer` renders, processes, recounts, and finishes `Chunk`.
- `lumberjack.normalizer` and `lumberjack.transformer`: built-in post-processing stages.
- `lumberjack.models` and `lumberjack.protocols`: shared state and extension contracts.

The removed `feller`, `sawyer`, and `scaler` modules are not compatibility paths.
`parser`, `splitter`, and `tokenizer` are the supported public component namespaces.

## Parsers and DocTree

`AutoParser` detects input in this order:

1. A `Path` or `Document.source_path` suffix.
2. The DOCX ZIP structure.
3. A leading HTML doctype or structural tag.
4. Markdown as the fallback.

A plain string is content, never an implicit filesystem path. Each format-specific
parser also accepts a raw text/bytes convenience value:

```python
from lumberjack.parser import MarkdownParser

document = MarkdownParser(disable_lheading=False).parse(
    markdown_text,
    document_title="Guide",
    metadata_overrides={"tenant": "docs"},
    source_path="imports/guide.md",
)
```

`DocTree.metadata` contains semantic metadata; `DocTree.source_path` independently records
provenance and becomes `Chunk.document_path`.

## Splitters and ChunkDrafts

Splitters accept the same budget and block options as the previous splitting pipeline:

```python
from lumberjack.splitter import SiblingSplitter

splitter = SiblingSplitter(
    tokenizer,
    max_tokens=1200,
    ideal_max_tokens_ratio=0.8,
    merge_below_ratio=0.125,
    skip_empty_sections=True,
    heading_sensitive=True,
    max_heading_level=None,
)

drafts = splitter.split(document)
```

- `SiblingSplitter` greedily packs adjacent sibling sections.
- `SubtreeSplitter` first collapses a fitting subtree, then falls back to sections.
- `SectionSplitter` emits direct section bodies recursively without subtree collapse.
- `Exact*Splitter` recount rendered candidates at every budget decision; unprefixed
  splitters use incremental estimates.

`ChunkDraft.token_count` is the split-time footprint. `ChunkFinalizer` writes it to
`Chunk.estimated_token_count` for incremental splitters and performs the authoritative
final recount after text processing. Exact splitters produce equal estimated and final
counts.

## Seasoning, planing, and finalizeing

The default `TextNormalizer` normalizes CRLF/CR to LF and removes BOM/NUL characters.
The default `TextTransformer` trims line endings and collapses repeated blank separators without
removing Markdown syntax.

`PlainTextTransformer` is an explicit opt-in for removing common Markdown/HTML surface
formatting while retaining readable content, code text, and block separation:

```python
from lumberjack import Lumberjack
from lumberjack.transformer import PlainTextTransformer

jack = Lumberjack(transformer=PlainTextTransformer())
chunks = jack.saw(markdown_text)
```

Custom `ParserProtocol`, `TokenizerProtocol`, `SplitterProtocol`, `TextNormalizerProtocol`, and
`TextTransformerProtocol` implementations can be injected through `Lumberjack(...)`.

## Typed block configuration

Python `block_options` accepts a sequence of `BlockConfig`, `MarkdownTableConfig`,
`HTMLTableConfig`, or `CustomBlockConfig`. Duplicate kinds and non-positive budgets are
rejected at construction time.

## CLI and Web API

The integration protocols intentionally retain their established domain-oriented names:

```bash
lumber guide.md --max-tokens 1200
lumber guide.md --tokenizer tiktoken --splitter sibling
lumber guide.md --splitter exact-sibling
lumber report.docx --input-format docx
lumberjack-serve --reload
```

- `POST /lumber/api/split/text`
- `POST /lumber/api/split/file`

CLI and Web fields remain `tokenizer` and `splitter`; the private integration adapter
translates them to Tokenizer and Splitter implementations. CLI output and Web responses retain
the existing serialized `Chunk` schema.

## Development

```bash
uv sync --group dev --group test --extra tokenizers --extra docx --extra web
UV_CACHE_DIR=/tmp/uvcache uv run ty check .
UV_CACHE_DIR=/tmp/uvcache uv run ruff check
UV_CACHE_DIR=/tmp/uvcache uv run ruff format --check
UV_CACHE_DIR=/tmp/uvcache uv run pytest
```

## License

MIT
