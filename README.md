# lumberjack

[中文文档](README.zh-CN.md)

`lumberjack` is a structure-aware Markdown splitter for long-document retrieval and RAG preprocessing.
It splits Markdown by document structure instead of fixed text windows.

The parser uses [`markdown-it-py`](https://markdown-it-py.readthedocs.io/en/latest/) in `gfm-like`
mode and normalizes its token stream into lumberjack's internal data model before chunking.

## What It Does

Core pipeline:

```text
Markdown text -> parser tokens -> DocumentAST -> splitter -> Chunk[]
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
uv run lumber path/to/file.md --max-tokens 1200 --merge-below-tokens 50 --format json
```

Show help:

```bash
uv run lumber --help
```

Supported CLI options today:

- `input`: Markdown file path
- `--output`: write output to a file instead of stdout
- `--format {json,markdown}`: output format, default `json`
- `--tokenizer {simple,tiktoken}`: token counting strategy, default `simple`
- `--parser {default,markdown-it}`: parser selector exposed by the CLI
- `--splitter {semantic,heading}`: splitting strategy, default `semantic`
- `--max-tokens`: maximum chunk budget, default `1200`
- `--merge-below-tokens`: soft threshold for small-chunk merging, default `50`
- `--overlap-tokens`: optional token overlap used only for text fallback splits, default `0`
- `--recursive-split`: split oversized direct section bodies when using `--splitter heading`
- `--retain-headings`: include heading context in rendered chunk text
- `--split-oversized-block <kind>`: opt in to splitting oversized `list`, `code_block`, `code_fence`, `table`, and other supported block kinds

Parser note:

- `default` and `markdown-it` both resolve to the `markdown-it-py` parser
- `MarkdownItParser` also supports `markdown-it-py` plugins through its constructor

### JSON Output

The JSON CLI output contains:

- `document`
- `chunk_count`
- `chunks`

Each chunk is serialized from the `Chunk` dataclass and includes fields such as:

- `chunk_id`
- `chunk_type`
- `text`
- `body`
- `token_count`
- `estimated_token_count`
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

The top-level Python API is intentionally small: pass Markdown text to `lumberjack.lumber()`
and receive a list of `Chunk` objects. File reading is handled by callers.

```python
from lumberjack import lumber

chunks = lumber(
    markdown_text,
    document_title="guide.md",
    max_tokens=1200,
    merge_below_tokens=50,
    overlap_tokens=0,
    retain_headings=True,
    merge_small_chunks=True,
    split_oversized_blocks=("list", "code_fence"),
    disable_lheading=False,
    tokenizer="simple",
    parser="default",
    splitter="semantic",
)

from mdit_py_plugins.tasklists import tasklists_plugin
from lumberjack.core.parser import MarkdownItParser

plugin_chunks = lumber(
    markdown_text,
    document_title="tasks.md",
    parser=MarkdownItParser(plugins=(tasklists_plugin,)),
)
```

Only `lumber` is exported from [`src/lumberjack/__init__.py`](/D:/coding/Python/lumberjack/src/lumberjack/__init__.py).
Advanced parser, splitter, tokenizer, and model types remain available from their internal modules.

## Internal Model

Main dataclasses in [`src/lumberjack/models.py`](/D:/coding/Python/lumberjack/src/lumberjack/models.py):

- `MarkdownInline`: normalized inline node with `kind`, `text`, `children`, and `attrs`
- `MarkdownBlock`: block node with rendered text, nested blocks, inline children, line range, and attrs
- `SectionNode`: heading-tree node with `path`, `blocks`, `children`, `start_line`, and `title_inlines`
- `DocumentAST`: root document object with `source`, `metadata`, and `reference_definitions`
- `Chunk`: finalized split unit with type, visible text, body-only text, heading path, and source metadata

## Parsing Coverage

The current parser normalizes these block-level structures:

- ATX headings
- Setext headings
- paragraphs
- block quotes
- ordered and unordered lists
- tables
- fenced code blocks
- indented code blocks
- HTML blocks
- thematic breaks
- link reference definitions metadata

The current parser captures these inline structures inside headings and paragraphs:

- text
- links
- images
- autolinks
- code spans
- emphasis
- strong emphasis
- strikethrough
- inline HTML
- soft and hard line breaks

The parser also preserves:

- heading title inlines
- reference link definitions in `DocumentAST.reference_definitions`
- source line ranges for headings and rendered blocks

Parser behavior note:

- `markdown-it-py` does not emit reference definition lines as visible `link_reference_definition` blocks
- plugin-generated block tokens are preserved as plugin-specific block kinds or raw markdown fallback blocks
- plugin-generated inline tokens are preserved when possible, with unknown inline containers keeping their child text intact

## Splitting Strategy

`lumber()` supports two splitter names:

- `semantic` (default): structure-first and budget-aware; it can merge adjacent
  sibling sections when they fit the same chunk.
- `heading`: emits one non-overlapping chunk per heading section direct body.
  Child sections are emitted as their own chunks, not repeated in parent chunks.

Semantic splitting follows this order:

1. Keep the whole document as one chunk if it already fits.
2. Otherwise split by heading sections.
3. If a section is too large, split by block boundaries.
4. If a block is still too large, fall back to paragraph, line, sentence, word, and finally hard splitting.

Important details:

- Heading context is preserved in `Chunk.text` when `retain_headings=True`
- Shared parent headings are deduplicated when sibling sections are merged into one chunk
- `Chunk.body` excludes the common heading prefix already represented by `Chunk.headings`
- `estimated_token_count` is the additive budget estimate used for splitting:
  section body, heading title, and subtree counts are cached bottom-up. Heading
  markers (the leading `#` run) and Markdown separators each count as one token.
  `token_count` is still counted once from the final rendered chunk body for
  reporting.
- `merge_below_tokens` is not a final minimum chunk size. It is a soft merge
  threshold for short tails produced by fragment or text fallback splitting:
  adjacent tails below this value are merged only when they share the same
  heading path and the estimated merged size still fits within `max_tokens`.
- Optional overlap is only applied when a single oversized block must be split by paragraph, line, sentence, word, or hard boundaries
- Oversized lists and code blocks stay intact by default, but can be made splittable via `split_oversized_blocks`
- Long URL-like spans are treated as unsplittable and will not be hard-split across chunks
- For `heading`, `recursive_split=False` keeps oversized section bodies intact.
  Set `recursive_split=True` to use the same block/text fallback for oversized
  direct section bodies.

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
script/                   Batch processing scripts (dataset download & split)
tests/                    Parser, splitter, and API tests
docs/                     Architecture and development notes
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
