# Lumberjack

Structure-aware Markdown, HTML, and DOCX splitting for RAG preprocessing.

Lumberjack separates parsing, tokenization, and splitting into explicit components. All
parsers produce the same `DocumentAST`, so every splitter works with every supported
format.

## Installation

```bash
pip install lumberjack

# Optional tokenizers, DOCX, and Web API support
pip install "lumberjack[tokenizers,docx,web]"
```

Python 3.10 or newer is required.

## Minimal API

The package root intentionally exposes only `lumber()`:

```python
from pathlib import Path

from lumberjack import lumber

chunks = lumber(Path("guide.md"), max_tokens=1200)
```

`lumber()` uses `AutoParser`, `ApproxByteTokenizer`, and the incremental
`SiblingSplitter`. Its complete signature is:

```python
lumber(
    source: str | bytes | Path,
    *,
    format: Literal["auto", "markdown", "html", "docx"] = "auto",
    max_tokens: int = 1200,
) -> list[Chunk]
```

Use the component API for any other configuration.

## Component pipeline

```python
from pathlib import Path

from lumberjack.block import BlockConfig, BlockKind, MarkdownTableConfig
from lumberjack.parser import AutoParser
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

document = parser.parse(Path("guide.md"))
chunks = splitter.split(document)
```

Public components own their implementations directly:

- `lumberjack.parser`: `AutoParser`, `MarkdownParser`, `HTMLParser`, `DocxParser`,
  and Markdown plugin extension types.
- `lumberjack.splitter`: incremental `SiblingSplitter`, `SubtreeSplitter`, and
  `SectionSplitter`, plus explicit `Exact*Splitter` implementations.
- `lumberjack.tokenizer`: `ApproxByteTokenizer`, `TiktokenTokenizer`, and
  `TransformersTokenizer`.
- `lumberjack.block`: typed block kinds and block configuration objects.
- `lumberjack.models`: the shared AST and `Chunk` output types.
- `lumberjack.protocols`: protocols for custom components.

There is no public or compatibility `lumberjack.core` package. Private
cross-component adapters live under `lumberjack._internal`.

## Parsing

### Automatic parser selection

```python
from lumberjack.parser import AutoParser

parser = AutoParser()
document = parser.parse(text, source_path="archive/guide.md")
```

In `format="auto"` mode, detection uses:

1. The suffix of a `Path` input or explicit `source_path`.
2. The DOCX ZIP structure.
3. A leading HTML doctype or structural HTML tag.
4. Markdown as the fallback.

A plain `str` is always document content. Use `Path("guide.md")` to read a file;
Lumberjack never treats an arbitrary string as an implicit filesystem path.

Force one parser with `AutoParser(format="markdown")`, `"html"`, or `"docx"`.

### Parser-specific settings

```python
from lumberjack.parser import MarkdownParser

# Setext headings are disabled by default.
parser = MarkdownParser(disable_lheading=False)
document = parser.parse(markdown_text)
```

Every parser accepts the same document-level keyword arguments:

```python
document = parser.parse(
    source,
    document_title="Guide",
    metadata_overrides={"tenant": "docs"},
    source_path="imports/guide.md",
)
```

`DocumentAST.metadata` contains semantic metadata extracted from front matter, HTML
metadata, or DOCX core properties. `metadata_overrides` supplements or overrides it.
Source provenance is stored separately in `DocumentAST.source_path`, which becomes
`Chunk.document_path`.

## Splitters

The unprefixed Python classes use incremental measurement:

```python
from lumberjack.splitter import SiblingSplitter

splitter = SiblingSplitter(
    tokenizer,
    max_tokens=1200,
    ideal_max_tokens_ratio=0.8,
    merge_below_ratio=0.125,
    skip_empty_sections=True,
    render_headings=True,
    max_heading_level=None,
)
```

- `SiblingSplitter`: greedily packs adjacent sibling sections.
- `SubtreeSplitter`: first collapses a fitting subtree, then falls back to sections.
- `SectionSplitter`: emits direct section bodies recursively; it has no
  `merge_below_ratio` argument because tail merging does not apply.
- `ExactSiblingSplitter`, `ExactSubtreeSplitter`, `ExactSectionSplitter`: fully recount
  rendered candidates at each budget decision.

Incremental chunks store the authoritative final recount in `token_count` and the
split-time estimate in `estimated_token_count`. Exact splitters make those values equal.

## Typed block configuration

Python `block_options` accepts a sequence of configuration objects, never a dictionary:

```python
from lumberjack.block import (
    BlockConfig,
    BlockKind,
    CustomBlockConfig,
    HTMLTableConfig,
    MarkdownTableConfig,
)

block_options = [
    BlockConfig(BlockKind.LIST, isolated=True),
    BlockConfig(BlockKind.CODE_FENCE, split=False),
    MarkdownTableConfig(max_tokens=500, repeat_header=True),
    HTMLTableConfig(max_tokens=500, repeat_header=False),
    CustomBlockConfig("callout", isolated=True),
]
```

Each built-in kind is selected by `BlockKind`; the table config classes select their
kind implicitly. `CustomBlockConfig` is reserved for parser-plugin block kinds.
Duplicate kinds and non-positive per-block budgets are rejected at construction time.

## Custom components

Implement the protocols from `lumberjack.protocols`, then compose objects directly:

```python
from lumberjack.parser import MarkdownParser

document = MarkdownParser().parse(markdown_text)
chunks = custom_splitter.split(document)
```

There is intentionally no public Pipeline, Builder, options aggregate, registry factory,
or module-level `parse()` function.

## CLI

```bash
lumber guide.md --max-tokens 1200
lumber guide.md --tokenizer tiktoken --splitter sibling
lumber guide.md --splitter exact-sibling
lumber report.docx --input-format docx
lumber guide.md --block-config table:isolated:500
```

Unprefixed CLI splitter names use incremental measurement. `incremental-*` remains an
equivalent explicit alias; `exact-*` selects full recounting. CLI output is JSON.

## Web API

```bash
lumberjack-serve --reload
```

- `POST /lumber/api/split/text`
- `POST /lumber/api/split/file`

The CLI and Web request fields remain integration-friendly mappings. Those boundary
layers convert external block JSON into the typed Python configuration objects.

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
