# Lumberjack

Structure-aware Markdown, HTML, and DOCX lumbering for RAG preprocessing.

Lumberjack models document processing as a real lumber pipeline:

```text
Tree -> Feller.fell() -> Log -> Sawyer.saw() -> Bundle[]
     -> Mill.mill() -> Seasoner -> Planer -> Chunk[]
```

## Installation

```bash
pip install lumberjack

# Optional scalers, DOCX, and Web API support
pip install "lumberjack[tokenizers,docx,web]"
```

Python 3.10 or newer is required.

## Main API

The package root exposes `Lumberjack` and `Tree`:

```python
from pathlib import Path

from lumberjack import Lumberjack, Tree

jack = Lumberjack(max_tokens=1200)

# Raw values are wrapped into Tree automatically.
chunks = jack.saw(Path("guide.md"))

# Tree carries format, title, metadata, and source provenance explicitly.
chunks = jack.saw(
    Tree(
        source=markdown_text,
        format="markdown",
        document_title="Guide",
        metadata_overrides={"tenant": "docs"},
        source_path="imports/guide.md",
    )
)
```

`Lumberjack()` defaults to `AutoFeller`, `ApproxByteScaler`, incremental
`SiblingSawyer`, `Seasoner`, `Planer`, and `Mill`. The same scaler instance is used for
split-budget estimates and final counts.

## Component pipeline

```python
from pathlib import Path

from lumberjack.block import BlockConfig, BlockKind, MarkdownTableConfig
from lumberjack.feller import AutoFeller
from lumberjack.mill import Mill
from lumberjack.models import Tree
from lumberjack.sawyer import SiblingSawyer
from lumberjack.scaler import TiktokenScaler

scaler = TiktokenScaler(model="gpt-4o-mini")
feller = AutoFeller()
sawyer = SiblingSawyer(
    scaler,
    max_tokens=1200,
    block_options=[
        MarkdownTableConfig(isolated=True, max_tokens=500),
        BlockConfig(BlockKind.CODE_FENCE, split=False),
    ],
)
mill = Mill(scaler)

log = feller.fell(Tree(Path("guide.md")))
bundles = sawyer.saw(log)
chunks = mill.mill(log, bundles)
```

Public components:

- `lumberjack.feller`: `AutoFeller`, `MarkdownFeller`, `HTMLFeller`, and
  `DocxFeller` turn `Tree` into the shared `Log` structure.
- `lumberjack.scaler`: `ApproxByteScaler`, `TiktokenScaler`, and
  `TransformersScaler` implement `encode()` and `scale()`.
- `lumberjack.sawyer`: incremental `SiblingSawyer`, `SubtreeSawyer`, and
  `SectionSawyer`, plus explicit `Exact*Sawyer` implementations, produce `Bundle`.
- `lumberjack.mill`: `Mill` renders, processes, recounts, and finishes `Chunk`.
- `lumberjack.seasoner` and `lumberjack.planer`: built-in post-processing stages.
- `lumberjack.models` and `lumberjack.protocols`: shared state and extension contracts.

The removed `parser`, `splitter`, `tokenizer`, and `core` packages are not compatibility
paths.

## Fellers and Log

`AutoFeller` detects input in this order:

1. A `Path` or `Tree.source_path` suffix.
2. The DOCX ZIP structure.
3. A leading HTML doctype or structural tag.
4. Markdown as the fallback.

A plain string is content, never an implicit filesystem path. Each format-specific
feller also accepts a raw text/bytes convenience value:

```python
from lumberjack.feller import MarkdownFeller

log = MarkdownFeller(disable_lheading=False).fell(
    markdown_text,
    document_title="Guide",
    metadata_overrides={"tenant": "docs"},
    source_path="imports/guide.md",
)
```

`Log.metadata` contains semantic metadata; `Log.source_path` independently records
provenance and becomes `Chunk.document_path`.

## Sawyers and Bundles

Sawyers accept the same budget and block options as the previous splitting pipeline:

```python
from lumberjack.sawyer import SiblingSawyer

sawyer = SiblingSawyer(
    scaler,
    max_tokens=1200,
    ideal_max_tokens_ratio=0.8,
    merge_below_ratio=0.125,
    skip_empty_sections=True,
    heading_sensitive=True,
    max_heading_level=None,
)

bundles = sawyer.saw(log)
```

- `SiblingSawyer` greedily packs adjacent sibling sections.
- `SubtreeSawyer` first collapses a fitting subtree, then falls back to sections.
- `SectionSawyer` emits direct section bodies recursively without subtree collapse.
- `Exact*Sawyer` recount rendered candidates at every budget decision; unprefixed
  sawyers use incremental estimates.

`Bundle.token_count` is the split-time footprint. `Mill` writes it to
`Chunk.estimated_token_count` for incremental sawyers and performs the authoritative
final recount after text processing. Exact sawyers produce equal estimated and final
counts.

## Seasoning, planing, and milling

The default `Seasoner` normalizes CRLF/CR to LF and removes BOM/NUL characters.
The default `Planer` trims line endings and collapses repeated blank separators without
removing Markdown syntax.

`PlainTextPlaner` is an explicit opt-in for removing common Markdown/HTML surface
formatting while retaining readable content, code text, and block separation:

```python
from lumberjack import Lumberjack
from lumberjack.planer import PlainTextPlaner

jack = Lumberjack(planer=PlainTextPlaner())
chunks = jack.saw(markdown_text)
```

Custom `FellerProtocol`, `ScalerProtocol`, `SawyerProtocol`, `SeasonerProtocol`, and
`PlanerProtocol` implementations can be injected through `Lumberjack(...)`.

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
translates them to Scaler and Sawyer implementations. CLI output and Web responses retain
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
