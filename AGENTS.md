# lumberjack Development Notes

## Project

The project is in the **development stage** and compatibility does not need to be considered. Allow all disruptive changes.

Markdown / DOCX document splitter for RAG preprocessing. Python 3.13+, `src/` layout, built with `hatchling` + `hatch-vcs`.

Current runtime dependencies:

- `markdown-it-py[linkify,plugins]>=4.0.0` for the default GFM-like parser
- `pyyaml>=6.0` for YAML front matter parsing

Optional dependencies:

- `tiktoken>=0.9.0`, `cachetools>=7.1.1` for model-based token counting (install via `--extra tokenizers`)
- `python-docx>=1.1.0` for DOCX document support (install via `--extra docx`)
- `fastapi>=0.115.0`, `uvicorn>=0.34.0`, `python-multipart>=0.0.18` for the web server (install via `--group web`)

## Commands

```bash
# Install dev, test, tokenizer, and DOCX dependencies
uv sync --group dev --group test --extra tokenizers --extra docx

# Install with web server support
uv sync --group web

# Run CLI (Markdown)
uv run lumber path/to/file.md --max-tokens 1200 --merge-below-tokens 50 -f json

# Run CLI (DOCX)
uv run lumber path/to/file.docx --input-format docx --max-tokens 1200 -f json

# Show CLI help
uv run lumber --help

# Run web server (development)
uv run lumberjack-serve --reload

# Run web server (production)
uv run lumberjack-serve --host 0.0.0.0 --port 8000

# Run tests
uv run pytest
uv run pytest tests/test_parser.py
uv run pytest tests/test_splitter.py
uv run pytest tests/test_docx_parser.py
uv run pytest tests/test_web.py

# Lint and format
uv run ruff check --fix
uv run ruff format

# Run Python scripts
uv run python xxx.py
```

## Architecture

Core pipeline:

```
Markdown text ----> MarkdownItParser ----> DocumentAST ----> Splitter ----> Chunk[]
DOCX binary  ----> DocxParser ----------------------------------------------> Chunk[]
```

Both formats produce the same `DocumentAST` (with `SectionNode` tree and `MarkdownBlock` children), so all splitters work with either format.

Main components:

### Shared (`src/lumberjack/core/`)

- **Models**: `src/lumberjack/core/models.py`
  - `MarkdownInline`, `MarkdownBlock`, `SectionNode`, `DocumentAST` — shared across formats
  - `BlockConfig`, `SplitOptions`, `Chunk` — configuration and output types
- **Protocols**: `src/lumberjack/core/protocols.py`
  - `TokenizerProtocol`, `MarkdownParserProtocol`, `SplitterProtocol`
- **Tokenizer**: `src/lumberjack/core/tokenizers.py`
  - `SimpleCharTokenizer` (default), `TiktokenTokenizer` (optional)
- **TextSplitter**: `src/lumberjack/core/text_splitter.py`
  - Handles oversized block splitting via paragraph/line/sentence/word/hard boundaries
  - Uses `HTMLTableParser` (from `core/html/table_parser.py`) to split oversized `html_table` blocks
- **Utilities**: `src/lumberjack/core/utils.py`, `src/lumberjack/core/block_config.py`

### Markdown (`src/lumberjack/core/markdown/`)

- **Parser**: `src/lumberjack/core/markdown/parser.py`
  - `MarkdownParser` aliases `MarkdownItParser`
  - Uses `MarkdownIt("gfm-like")` with built-in plugins
  - `MarkdownItParser(disable_lheading=True)` to disable Setext heading parsing
  - Parses YAML front matter, preserves heading hierarchy, inlines, reference definitions, line ranges
- **Splitter**: `src/lumberjack/core/markdown/splitter.py`
  - `_BaseMarkdownSplitter` provides shared state and helpers
  - `RecursiveMarkdownSplitter` (registry: "default", "recursive") — structure-first, budget-aware
  - `SectionMarkdownSplitter` (registry: "section") — one chunk per heading section
  - `SPLITTER_REGISTRY` and `create_splitter()` factory
- **Plugins**: `src/lumberjack/core/markdown/plugins/`
  - `brackets_math_plugin`: `\[...\]` block math and `\(...\)` inline math syntax
- **Visitor**: `src/lumberjack/core/markdown/visitor.py` — lightweight AST visitor hooks

### DOCX (`src/lumberjack/core/docx/`)

- **Parser**: `src/lumberjack/core/docx/parser.py`
  - `DocxParser` — parses DOCX into `DocumentAST`
  - Maps Heading styles -> `SectionNode`, paragraphs -> `paragraph`, tables -> `table`, lists -> `list`, etc.
  - Iterates body elements in document order to preserve paragraph/table sequence
  - Extracts core properties as document metadata

### HTML (`src/lumberjack/core/html/`)

- **Parser**: `src/lumberjack/core/html/parser.py`
  - `HTMLParser` — parses HTML into `DocumentAST`, mirroring `MarkdownItParser` and `DocxParser`
  - Built on stdlib `html.parser.HTMLParser` (aliased internally as `_StdlibHTMLParser` to avoid name shadowing)
  - `_HTMLDocumentBuilder` is the event-driven internal builder
  - Maps headings -> `SectionNode`, paragraphs -> `paragraph`, tables -> `html_table`, lists -> `list`, etc.
- **Table utility**: `src/lumberjack/core/html/table_parser.py`
  - `HTMLTableParser` + `HTMLTable`/`HTMLTableRow`/`HTMLTableCell` dataclasses
  - Consumed by `markdown/parser.py` (to detect tables inside `html_block`) and `text_splitter.py` (to split oversized `html_table` blocks); not used by `HTMLParser` itself

### Public API

- `src/lumberjack/__init__.py` — `lumber()` function
  - Accepts `str | bytes | Path` input
  - Auto-detects format or uses explicit `format` parameter (`"auto"`, `"markdown"`, `"docx"`)

### Web API / UI

- **Web API**: `src/lumberjack/web/` — FastAPI with `/split/text` and `/split/file` endpoints
- **Web UI**: `lumberjack_webui/` — React 19 + TypeScript + Vite

## Data Model

Defined in `src/lumberjack/core/models.py`.

## Web API

Implemented in `src/lumberjack/web/`.

- `POST /lumber/api/split/text` — JSON body with `text` and split options
- `POST /lumber/api/split/file` — multipart form with `file` upload and split options
  - Supports `input_format` form field (`"auto"`, `"markdown"`, `"docx"`)
  - Auto-detects format from file extension when `"auto"`
- Response: JSON with `document`, `chunk_count`, and `chunks` array
- Server CLI: `lumberjack-serve` with `--host`, `--port`, `--reload`

## CLI Behavior

Implemented in `src/lumberjack/cli.py`.

- Input is a Markdown (`.md`) or DOCX (`.docx`) file path
- `--input-format`: `auto` (detect from extension), `markdown`, or `docx`
- Output format: JSON only
- Tokenizers: `simple`, `tiktoken`
- Splitter choices: `recursive`, `section` (CLI default: `recursive`)
- `--recursive-split` enables block/text fallback for oversized section bodies
- `--block-config KIND[:isolated][:nosplit][:TOKENS]` per-block-kind config; repeatable
- JSON output serializes dataclasses with `dataclasses.asdict`

## Splitting Rules

- Whole document is kept as one chunk when it already fits the budget
- `RecursiveMarkdownSplitter` (default): merges adjacent sibling sections when they fit within `max_tokens`
- `SectionMarkdownSplitter`: emits one chunk per heading section direct body; child sections become separate chunks
- Text fallback order is paragraph break -> line break -> sentence -> word -> hard split
- `Chunk.body` always includes rendered heading context; shared parent headings are deduplicated
- `skip_empty_sections=True` discards chunks that contain only a heading with no body content
- `recursive_split=True` enables block/text fallback for oversized section bodies in `SectionMarkdownSplitter`
- `block_options` maps block kinds to `BlockConfig` (per-kind `isolated`, `split`, `max_tokens`)

## Constraints

- Markdown and DOCX are the supported input formats
- Fenced code blocks are preserved intact even when they exceed `max_tokens` (unless `code_block`/`code_fence` has `split=True`)
- CLI should stay orchestration-only; parsing/splitting logic belongs in `src/lumberjack/core/`
- There is no LangChain dependency

## Testing

Tests use `pytest`. `tests/conftest.py` adds `src/` to `sys.path`.

Current test areas:

- Markdown parser heading-tree construction, inlines, line ranges
- DOCX parser heading parsing, table extraction, list detection, section tree structure
- Section-aware chunking, budget management, merging
- Public API (`lumber()`) with Markdown and DOCX input
- Web API split with text input, file upload, error handling, and full options

After Python code changes:

1. Run `uv run ruff check --fix`
2. Review whether `--unsafe-fixes` is actually needed before using it
3. Run `uv run ruff format`
4. Run the relevant `pytest` scope

## Code Organization

```
src/lumberjack/
    __init__.py                     # Public API: lumber()
    cli.py                          # CLI orchestration
    web/                            # FastAPI layer
    core/
        __init__.py                 # Re-exports
        models.py                   # Shared data models
        protocols.py                # Protocol interfaces
        tokenizers.py               # Tokenizer implementations
        text_splitter.py            # Generic TextSplitter
        block_config.py             # Block-kind parsing helpers
        utils.py                    # Rendering helpers
        markdown/
            __init__.py
            parser.py               # MarkdownItParser
            splitter.py             # _BaseMarkdownSplitter + Recursive/Section
            visitor.py              # MarkdownAstVisitor
            plugins/                # markdown-it plugins
        docx/
            __init__.py
            parser.py               # DocxParser
        html/
            __init__.py
            parser.py               # HTMLParser + _HTMLDocumentBuilder
            table_parser.py         # HTMLTableParser + HTMLTable*
lumberjack_webui/                   # React + TypeScript frontend
tests/
    test_api.py
    test_parser.py
    test_splitter.py
    test_docx_parser.py
    test_utils.py
    test_web.py
    fixtures/
        markdown/
        docx/
```
