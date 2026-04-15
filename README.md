# lumberjack

`lumberjack` is a structure-aware Markdown splitter for long-document retrieval and RAG preprocessing.
It parses Markdown into an internal AST first, then splits by document structure instead of fixed text windows.

The current implementation uses [`marko`](https://github.com/frostming/marko) to build a CommonMark-style AST,
normalizes that tree into lumberjack's own data model, and then produces semantic chunks with heading context,
line ranges, and document metadata.

## What It Does

Core pipeline:

```text
Markdown text -> marko AST -> DocumentAST -> MarkdownSplitter -> Chunk[]
```

Current behavior:

- Builds a heading tree with section-local blocks
- Preserves block structure for paragraphs, lists, block quotes, code blocks, HTML blocks, and thematic breaks
- Captures inline nodes for headings and paragraphs
- Tracks link reference definitions in the document model
- Preserves line ranges for headings and blocks when source matching is possible
- Splits by whole document -> section tree -> block/text fallback
- Keeps fenced code blocks intact even when they exceed the token budget

## Install

Runtime install:

```bash
uv sync
```

Development install with tests, linting, and optional `tiktoken` support:

```bash
uv sync --group dev --group test --extra tokenizers
```

## CLI

Basic usage:

```bash
uv run lumberjack path/to/file.md --max-tokens 1200 --min-tokens 50 --format json
```

Show help:

```bash
uv run lumberjack --help
```

Supported CLI options today:

- `input`: Markdown file path
- `--output`: write output to a file instead of stdout
- `--format {json,markdown}`: output format, default `json`
- `--tokenizer {simple,tiktoken}`: token counting strategy, default `simple`
- `--parser {simple,marko}`: parser selector exposed by the CLI
- `--max-tokens`: maximum chunk budget, default `1200`
- `--min-tokens`: threshold used by small-chunk merging, default `50`
- `--overlap-tokens`: optional token overlap used only for text fallback splits, default `0`
- `--retain-headings`: include heading context in rendered chunk text

Parser note:

- The CLI still exposes `simple` and `marko`, but both names currently resolve to the same CommonMark parser implementation in `src/lumberjack/core/parser.py`.

### JSON Output

The JSON CLI output contains:

- `document`
- `chunk_count`
- `chunks`

Each chunk is serialized from the `Chunk` dataclass and includes fields such as:

- `chunk_id`
- `text`
- `body`
- `token_count`
- `headings`
- `section_level`
- `document_title`
- `document_path`
- `start_line`
- `end_line`

### Markdown Output

`--format markdown` renders each chunk as Markdown and prefixes it with an HTML comment showing the chunk index and token count.

## Python API

The public API lives in [`src/lumberjack/api.py`](/D:/coding/Python/lumberjack/src/lumberjack/api.py).

```python
from lumberjack import parse_markdown, split_markdown_file, split_markdown_text

document = parse_markdown(
    markdown_text,
    document_title="guide.md",
    document_metadata={"path": "/abs/path/guide.md"},
)

chunks = split_markdown_text(
    markdown_text,
    document_title="guide.md",
    max_tokens=1200,
    min_tokens=50,
    overlap_tokens=0,
    retain_headings=True,
    merge_small_chunks=True,
    tokenizer="simple",
)

file_chunks = split_markdown_file(
    "docs/guide.md",
    max_tokens=1200,
    min_tokens=50,
    overlap_tokens=0,
)
```

Public types exported from [`src/lumberjack/__init__.py`](/D:/coding/Python/lumberjack/src/lumberjack/__init__.py):

- `Chunk`
- `DocumentAST`
- `MarkdownBlock`
- `MarkdownInline`
- `SectionNode`
- `SplitOptions`
- `MarkdownParser`
- `MarkdownSplitter`
- `SimpleCharTokenizer`
- `TiktokenTokenizer`

## Internal Model

Main dataclasses in [`src/lumberjack/models.py`](/D:/coding/Python/lumberjack/src/lumberjack/models.py):

- `MarkdownInline`: normalized inline node with `kind`, `text`, `children`, and `attrs`
- `MarkdownBlock`: block node with rendered text, nested blocks, inline children, line range, and attrs
- `SectionNode`: heading-tree node with `path`, `blocks`, `children`, `start_line`, and `title_inlines`
- `DocumentAST`: root document object with `source`, `metadata`, and `reference_definitions`
- `Chunk`: finalized split unit with visible text, body-only text, heading path, and source metadata

## Parsing Coverage

The current parser normalizes these block-level structures:

- ATX headings
- paragraphs
- block quotes
- ordered and unordered lists
- fenced code blocks
- indented code blocks
- HTML blocks
- thematic breaks
- link reference definitions

The current parser captures these inline structures inside headings and paragraphs:

- text
- links
- images
- autolinks
- code spans
- emphasis
- strong emphasis
- inline HTML
- soft and hard line breaks

The parser also preserves:

- heading title inlines
- reference link definitions in `DocumentAST.reference_definitions`
- source line ranges for headings and rendered blocks

## Splitting Strategy

Splitting is structure-first and budget-aware:

1. Keep the whole document as one chunk if it already fits.
2. Otherwise split by heading sections.
3. If a section is too large, split by block boundaries.
4. If a block is still too large, fall back to paragraph, line, sentence, word, and finally hard splitting.

Important details:

- Heading context is preserved in `Chunk.text` when `retain_headings=True`
- Shared parent headings are deduplicated when sibling sections are merged into one chunk
- `Chunk.body` excludes the common heading prefix already represented by `Chunk.headings`
- Small-chunk merging only happens for adjacent chunks with the same heading path
- Optional overlap is only applied when a single oversized block must be split by paragraph, line, sentence, word, or hard boundaries
- Fenced code blocks are emitted intact even when they exceed `max_tokens`

## Tokenizers

Available tokenizer implementations in [`src/lumberjack/core/tokenizers.py`](/D:/coding/Python/lumberjack/src/lumberjack/core/tokenizers.py):

- `SimpleCharTokenizer`: counts characters
- `TiktokenTokenizer`: counts model tokens via `tiktoken`

If `tiktoken` is not installed and `TiktokenTokenizer` is requested, the library raises a runtime error with installation guidance.

## Repository Layout

```text
src/lumberjack/base/      Protocol interfaces
src/lumberjack/core/      Parser, splitter, tokenizer, and visitor implementations
src/lumberjack/api.py     Public Python API
src/lumberjack/models.py  Internal data models
src/lumberjack/utils.py   Markdown rendering helpers
src/lumberjack/main.py    CLI orchestration
tests/                    Parser, splitter, and API tests
docs/                     Architecture and development notes
demo.py                   Reference-only prototype material
```

## Testing

Run the full test suite:

```bash
uv run pytest
```

Run individual modules:

```bash
uv run pytest tests/test_parser.py
uv run pytest tests/test_splitter.py
uv run pytest tests/test_api.py
```

Lint and format:

```bash
uv run ruff check --fix
uv run ruff format
```

## Current Limits

`lumberjack` is intentionally focused on semantic splitting, not perfect Markdown round-tripping.

Current limits and notes:

- Markdown only; no PDF, HTML, or DOCX ingestion pipeline is planned in this package
- The parser is CommonMark-oriented, not a full GitHub-Flavored Markdown implementation
- Some rendered block text is normalized rather than preserved byte-for-byte
- `demo.py` is not part of the production package
- The CLI parser selector is currently a compatibility surface, not multiple real parser backends

## Status

The current repository already includes:

- parser tests for heading-tree construction, code-fence heading safety, CommonMark block/inline normalization, and line-range preservation
- splitter tests for whole-document fits, recursive section descent, heading deduplication, heading-hidden rendering, and chunk body behavior
- API tests for file/text parity and metadata propagation

That makes the project a solid base for section-aware Markdown chunking, while leaving room for future work on richer metadata and additional Markdown dialect support.
