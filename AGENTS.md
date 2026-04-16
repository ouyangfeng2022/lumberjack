# lumberjack Development Notes

## Project

AST-driven Markdown document splitter for RAG preprocessing. Python 3.13+, `src/` layout, built with `hatchling` + `hatch-vcs`.

Current runtime dependency:

- `markdown-it-py` for the default GFM-like parser

Optional dependency:

- `tiktoken` for model-based token counting

## Commands

```bash
# Install dev, test, and optional tokenizer dependencies
uv sync --group dev --group test --extra tokenizers

# Run CLI
uv run lumberjack path/to/file.md --max-tokens 1200 --min-tokens 50 --format json

# Show CLI help
uv run lumberjack --help

# Run tests
uv run pytest
uv run pytest tests/test_parser.py
uv run pytest tests/test_splitter.py

# Lint and format
uv run ruff check --fix
uv run ruff format
```

## Architecture

Core pipeline:

`Markdown text -> parser tokens/AST -> DocumentAST -> MarkdownSplitter -> Chunk[]`

Main components:

- **Parser**: `src/lumberjack/core/parser.py`
  - `MarkdownParser` currently aliases `MarkdownItParser`
  - Uses `MarkdownIt("gfm-like")` token streams for the default parser
  - Preserves heading hierarchy, block content, inline structure, reference definitions, and line ranges
- **Splitter**: `src/lumberjack/core/splitter.py`
  - Splits by whole document first, then section tree, then block/text fallback
  - Preserves heading context when enabled
  - Deduplicates shared parent headings in merged chunks
  - Never splits fenced code blocks, even when oversized
- **Tokenizer**: `src/lumberjack/core/tokenizers.py`
  - `SimpleCharTokenizer` is the default
  - `TiktokenTokenizer` is optional
- **Public API**: `src/lumberjack/api.py`
  - `parse_markdown`
  - `split_markdown_text`
  - `split_markdown_file`

Protocol interfaces live in `src/lumberjack/base/interfaces.py`. Data models use `@dataclass(slots=True)`.

## Data Model

Defined in `src/lumberjack/models.py`:

- `MarkdownInline`: normalized inline node with `kind`, `text`, `children`, and `attrs`
- `MarkdownBlock`: block node with rendered text, line range, inline children, nested blocks, and attrs
- `SectionNode`: heading-tree node with `path`, `blocks`, `children`, and title inline nodes
- `DocumentAST`: parsed document with `root`, raw `source`, `metadata`, and `reference_definitions`
- `SplitOptions`: `max_tokens`, `min_tokens`, `retain_headings`, `merge_small_chunks`
- `Chunk`: final chunk payload with `text`, `body`, `token_count`, `headings`, document metadata, and line range

## CLI Behavior

Implemented in `src/lumberjack/main.py`.

- Input is a Markdown file path
- Output formats: `json` or `markdown`
- Tokenizers: `simple`, `tiktoken`
- Parser choices exposed by CLI: `default`, `markdown-it`
- `--retain-headings` is opt-in on the CLI
- JSON output serializes dataclasses with `dataclasses.asdict`

## Current Parsing Coverage

The parser currently normalizes these block-level structures:

- headings
- paragraphs
- block quotes
- lists and list items
- tables
- fenced code blocks
- indented code blocks
- HTML blocks
- thematic breaks
- link reference definitions metadata

The parser currently captures these inline structures in headings and paragraphs:

- text
- links
- images
- autolinks
- code spans
- emphasis / strong emphasis
- strikethrough
- inline HTML
- soft and hard line breaks

## Splitting Rules

- Whole document is kept as one chunk when it already fits the budget
- Otherwise the splitter descends through heading sections before falling back to block/text splitting
- Text fallback order is paragraph break -> line break -> sentence -> word -> hard split
- `retain_headings=True` includes heading context in `Chunk.text`
- `Chunk.body` excludes the common heading prefix that is already represented by `Chunk.headings`
- Small chunks are merged only when they share the same heading path and still fit within `max_tokens`

## Constraints

- Markdown only; no PDF/HTML/DOCX ingestion pipeline is planned here
- `demo.py` is reference material, not production implementation
- Fenced code blocks are preserved intact even when they exceed `max_tokens`
- CLI should stay orchestration-only; parsing/splitting logic belongs in `src/lumberjack/core/`
- There is no LangChain dependency

## Testing

Tests use `pytest`. `tests/conftest.py` adds `src/` to `sys.path`.

Current test areas:

- parser heading-tree construction
- ignoring heading-like text inside fenced code
- default parser routing
- CommonMark block and inline normalization
- markdown-it parser coverage for Setext headings, tables, strikethrough, and linkify autolinks
- line-range preservation
- section-aware chunking
- whole-document fit checks
- recursive descent into child sections
- merged heading deduplication
- hidden-heading rendering behavior
- chunk metadata from file and text APIs

When changing parser or splitter behavior:

1. Update or add fixtures in `tests/fixtures/markdown/`
2. Update implementation in `src/lumberjack/core/` and public API if needed
3. Add or update assertions in `tests/test_parser.py`, `tests/test_splitter.py`, and `tests/test_api.py`

After Python code changes:

1. Run `uv run ruff check --fix`
2. Review whether `--unsafe-fixes` is actually needed before using it
3. Run `uv run ruff format`
4. Run the relevant `pytest` scope

## Code Organization

- `src/lumberjack/base/` - protocol interfaces
- `src/lumberjack/core/parser.py` - parser factory and default parser alias
- `src/lumberjack/core/splitter.py` - section/block/text chunking
- `src/lumberjack/core/tokenizers.py` - tokenizer implementations
- `src/lumberjack/core/visitor.py` - lightweight AST visitor hooks
- `src/lumberjack/api.py` - public Python API
- `src/lumberjack/models.py` - internal data models
- `src/lumberjack/utils.py` - Markdown rendering helpers
- `src/lumberjack/main.py` - CLI orchestration only

## Documentation Notes

Keep docs aligned with the code, especially when any of these change:

- CLI flags or defaults
- parser coverage
- tokenizer names
- chunk metadata fields
- test commands or dependency groups
- parser implementation strategy
