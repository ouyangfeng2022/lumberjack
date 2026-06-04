# lumberjack

[中文文档](README.zh-CN.md)

`lumberjack` is a structure-aware Markdown splitter for long-document retrieval and RAG preprocessing.
It splits Markdown by document structure instead of fixed text windows.

The parser uses [`markdown-it-py`](https://markdown-it-py.readthedocs.io/en/latest/) in `gfm-like`
mode with built-in plugins for LaTeX math (dollarmath and bracket syntax), YAML front matter,
and custom bracket math. It normalizes the token stream into lumberjack's internal data model before chunking.

## What It Does

Core pipeline:

```text
Markdown text -> parser tokens -> DocumentAST -> splitter -> Chunk[]
```

Current behavior:

- Builds a heading tree with section-local blocks
- Parses YAML front matter; resolves document title from user input, front matter, or first H1
- Preserves block structure for paragraphs, lists, block quotes, code blocks, HTML blocks, and math blocks
- Captures inline nodes for headings and paragraphs including math inline and footnote references
- Tracks link reference definitions in the document model
- Preserves line ranges for headings and blocks when source matching is possible
- Splits by whole document -> section tree -> block/text fallback
- Keeps fenced code blocks intact by default even when they exceed the token budget
- Keeps front matter as a normal block; skips empty heading-only sections
- Ignores thematic breaks during parsing, except when they delimit YAML front matter

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
- `--splitter {recursive,section}`: splitting strategy, default `recursive`
- `--max-tokens`: maximum chunk budget, default `1200`
- `--ideal-max-tokens-ratio`: preferred split budget as a ratio of `--max-tokens`, default `0.8`
- `--merge-below-tokens`: soft threshold for small-chunk merging, default `50`
- `--overlap-tokens`: optional token overlap used only for text fallback splits, default `0`
- `--recursive-split`: split oversized direct section bodies when using `--splitter section`
- `--block-handling KIND:POLICY`: override a block kind's merge policy; repeat to add multiple. Policies: `default`, `isolate`
- `--nosplit-kinds KIND,...`: block kinds that should not be split when oversized, default empty
- `--block-max-tokens KIND:TOKENS`: override the split budget for a block kind; repeat to add multiple
- `--disable-lheading`: disable Setext heading parsing

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

The public API lives in [`src/lumberjack/api.py`](src/lumberjack/api.py).

The top-level Python API is intentionally small: pass Markdown text to `lumberjack.lumber()`
and receive a list of `Chunk` objects. File reading is handled by callers.

```python
from lumberjack import lumber

chunks = lumber(
    markdown_text,
    document_title="guide.md",
    max_tokens=1200,
    ideal_max_tokens_ratio=0.8,
    merge_below_tokens=50,
    overlap_tokens=0,
    merge_small_chunks=True,
    skip_empty_sections=True,
    block_handling={"table": "isolate"},
    nosplit_kinds={"code_fence"},
    block_max_tokens={"table": 800},
    recursive_split=False,
    disable_lheading=False,
    tokenizer="simple",
    parser="default",
    splitter="recursive",
)

from mdit_py_plugins.tasklists import tasklists_plugin
from lumberjack.core.parser import MarkdownItParser

plugin_chunks = lumber(
    markdown_text,
    document_title="tasks.md",
    parser=MarkdownItParser(plugins=(tasklists_plugin,)),
)
```

Only `lumber` is exported from [`src/lumberjack/__init__.py`](src/lumberjack/__init__.py).
Advanced parser, splitter, tokenizer, and model types remain available from their internal modules.

## Internal Model

Main dataclasses in [`src/lumberjack/models.py`](src/lumberjack/models.py):

- `MarkdownInline`: normalized inline node with `kind`, `text`, `children`, and `attrs`
- `MarkdownBlock`: block node with rendered text, nested blocks, inline children, line range, and attrs
- `SectionNode`: heading-tree node with `path`, `blocks`, `children`, `start_line`, `title_inlines`, and `index`
- `DocumentAST`: root document object with `source`, `metadata`, and `reference_definitions`; title resolved from front matter or first H1
- `Chunk`: finalized split unit with `chunk_id`, `chunk_type`, visible text (`body`), heading path, token counts, and source metadata

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
- link reference definitions
- YAML front matter
- math blocks (`$$...$$`)
- math blocks with equation numbers
- bracket math blocks (`\[...\]`)
- bracket math blocks with equation numbers (`\[...\](label)`)
- plugin-generated blocks preserved as plugin-specific kinds

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
- math inline (`$...$`)
- bracket math inline (`\(...\)`)
- footnote references and anchors
- plugin-generated inlines preserved with source token metadata

The parser also preserves:

- heading title inlines
- reference link definitions in `DocumentAST.reference_definitions`
- source line ranges for headings and rendered blocks

Parser behavior note:

- `markdown-it-py` does not emit reference definition lines as visible `link_reference_definition` blocks
- plugin-generated block tokens are preserved as plugin-specific block kinds or raw markdown fallback blocks
- plugin-generated inline tokens are preserved when possible, with unknown inline containers keeping their child text intact

## Splitting Strategy

The splitter registry supports these names:

- `recursive` / `default`: `RecursiveMarkdownSplitter` — structure-first and budget-aware; it can merge adjacent sibling sections when they fit the same chunk.
- `section`: `SectionMarkdownSplitter` — emits one non-overlapping chunk per heading section direct body. Child sections are emitted as their own chunks, not repeated in parent chunks.

The API default is `splitter="recursive"`.

Recursive splitting follows this order:

1. Keep the whole document as one chunk if it already fits.
2. Otherwise split by heading sections.
3. If a section is too large, split by block boundaries.
4. If a block is still too large, fall back to paragraph, line, sentence, word, and finally hard splitting.

Important details:

- Heading context is always preserved in `Chunk.body`
- Shared parent headings are deduplicated when sibling sections are merged into one chunk
- `estimated_token_count` is the additive budget estimate used for splitting:
  section body, heading title, and subtree counts are cached bottom-up. Heading
  markers (the leading `#` run) and Markdown separators each count as one token.
  `token_count` is still counted once from the final rendered chunk body for
  reporting.
- `ideal_max_tokens_ratio` sets the preferred split budget as a ratio of
  `max_tokens`. Initial section, block, and text fallback splits target this
  ideal budget; small-chunk merge passes can accumulate chunks up to the hard
  `max_tokens` limit.
- `merge_below_tokens` is not a final minimum chunk size. It is a soft merge
  threshold for adjacent same-parent chunks: tails below this value are merged
  bottom-up when the estimated merged size still fits within `max_tokens`.
- Optional overlap is only applied when a single oversized block must be split by paragraph, line, sentence, word, or hard boundaries
- All known block kinds are splittable by default. Use `nosplit_kinds` to keep selected oversized block kinds intact.
- Oversized Markdown pipe tables are split by rows. When a header delimiter row is detected, each table fragment repeats the original header and delimiter row. If a single data row with its header exceeds the budget, that row is kept as a valid oversized table fragment.
- `block_handling` controls merge policy only. Set a kind to `isolate` to emit that block kind as independent chunks instead of merging it with adjacent content.
- `block_max_tokens` can override the split budget for specific block kinds such as `table`.
- Long URL-like spans are treated as unsplittable and will not be hard-split across chunks
- YAML front matter is handled as a normal `front_matter` block. Use `block_handling={"front_matter": "isolate"}` when it should be emitted as its own chunk.
- `skip_empty_sections=True` discards chunks that contain only a heading with no body content
- Front matter delimiters are preserved inside the `front_matter` block; other thematic breaks are ignored during parsing
- For `section` splitter, `recursive_split=False` keeps oversized section bodies intact.
  Set `recursive_split=True` to use the same block/text fallback for oversized
  direct section bodies.

## Tokenizers

Available tokenizer implementations in [`src/lumberjack/core/tokenizers.py`](src/lumberjack/core/tokenizers.py):

- `SimpleCharTokenizer`: counts characters
- `TiktokenTokenizer`: counts model tokens via `tiktoken` with LRU cache

If `tiktoken` is not installed and `TiktokenTokenizer` is requested, the library raises a runtime error with installation guidance.

## Repository Layout

```text
src/lumberjack/base/          Protocol interfaces
src/lumberjack/core/          Parser, splitter, tokenizer, and visitor implementations
src/lumberjack/core/plugins/  Custom markdown-it plugins (bracket math)
src/lumberjack/api.py         Public Python API
src/lumberjack/models.py      Internal data models
src/lumberjack/utils.py       Markdown rendering helpers
src/lumberjack/main.py        CLI orchestration
src/lumberjack/web/           FastAPI web layer (app, routes, static serving)
lumberjack_webui/             React + TypeScript frontend
script/                       Batch processing scripts
tests/                        Parser, splitter, API, and web tests
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
uv run pytest tests/test_web.py
```

Lint and format:

```bash
uv run ruff check --fix
uv run ruff format
```
