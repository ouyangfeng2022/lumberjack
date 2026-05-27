# lumberjack Development Notes

## Project

Markdown document splitter for RAG preprocessing. Python 3.13+, `src/` layout, built with `hatchling` + `hatch-vcs`.

Current runtime dependencies:

- `markdown-it-py[linkify,plugins]>=4.0.0` for the default GFM-like parser
- `pyyaml>=6.0` for YAML front matter parsing

Optional dependencies:

- `tiktoken>=0.9.0`, `cachetools>=7.1.1` for model-based token counting (install via `--extra tokenizers`)
- `fastapi>=0.115.0`, `uvicorn>=0.34.0`, `python-multipart>=0.0.18` for the web server (install via `--group web`)

## Commands

```bash
# Install dev, test, and optional tokenizer dependencies
uv sync --group dev --group test --extra tokenizers

# Install with web server support
uv sync --group web

# Run CLI
uv run lumber path/to/file.md --max-tokens 1200 --merge-below-tokens 50 --format json

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
uv run pytest tests/test_web.py

# Lint and format
uv run ruff check --fix
uv run ruff format

# Run Python scripts
uv run python xxx.py
```

## Architecture

Core pipeline:

`Markdown text -> parser tokens -> DocumentAST -> _BaseMarkdownSplitter -> Chunk[]`

Main components:

- **Parser**: `src/lumberjack/core/parser.py`
  - `MarkdownParser` currently aliases `MarkdownItParser`
  - Uses `MarkdownIt("gfm-like")` with built-in plugins: `dollarmath_plugin`, `front_matter_plugin`, `brackets_math_plugin`
  - Supports `disable_lheading` to disable Setext heading parsing
  - Parses YAML front matter and resolves document title from: user-provided > front matter `title` > first H1 > "Anonymous"
  - Preserves heading hierarchy, block content, inline structure, reference definitions, and line ranges
- **Plugins**: `src/lumberjack/core/plugins/`
  - `brackets_math_plugin`: adds `\[...\]` block math and `\(...\)` inline math syntax support
- **Splitter**: `src/lumberjack/core/splitter.py`
  - `_BaseMarkdownSplitter` provides shared state and helpers (front matter isolation, chunk finalization, token measurement)
  - `RecursiveMarkdownSplitter` (registry: "default", "recursive"): structure-first, budget-aware; merges adjacent sibling sections when they fit
  - `SectionMarkdownSplitter` (registry: "section"): one chunk per heading section direct body; child sections are separate chunks
  - `TextSplitter`: handles oversized block splitting via paragraph/line/sentence/word/hard boundaries
  - Thematic breaks are attached to preceding blocks of kind paragraph, blockquote, html_block, math_block, or math_block_eqno
  - Front matter is isolated as the first chunk when `isolate_front_matter=True`
  - Empty sections (heading-only, no body) are skipped when `skip_empty_sections=True`
- **Tokenizer**: `src/lumberjack/core/tokenizers.py`
  - `SimpleCharTokenizer` is the default (counts characters)
  - `TiktokenTokenizer` is optional (model-based token counting with LRU cache)
- **Public API**: `src/lumberjack/api.py`
  - `lumber`
- **Web API**: `src/lumberjack/web/`
  - FastAPI application with `POST /lumber/api/split` endpoint
  - Accepts text input or file upload with all split options
  - Serves built frontend from `static/` in production
  - CLI: `lumberjack-serve` (`--host`, `--port`, `--reload`)
- **Web UI**: `lumberjack_webui/`
  - React 19 + TypeScript + Vite frontend
  - Dual input: text area or file upload
  - Full split options UI (basic + advanced)
  - Chunk result visualization with token counts and heading breadcrumbs
  - Dev proxy: `/lumber` -> `localhost:8000`; build output -> `src/lumberjack/web/static/`

Protocol interfaces live in `src/lumberjack/base/interfaces.py`. Data models use `@dataclass(slots=True)`.

## Data Model

Defined in `src/lumberjack/models.py`:

- `MarkdownInline`: normalized inline node with `kind`, `text`, `children`, and `attrs`
- `MarkdownBlock`: block node with rendered text, line range, inline children, nested blocks, and attrs
- `SectionNode`: heading-tree node with `path`, `blocks`, `children`, `start_line`, `title_inlines`, and `index`
- `DocumentAST`: parsed document with `root`, raw `source`, `metadata`, and `reference_definitions`; title resolved from front matter or first H1
- `SplitOptions`: `max_tokens`, `merge_below_tokens`, `overlap_tokens`, `merge_small_chunks`, `isolate_front_matter`, `skip_empty_sections`, `recursive_split`, `split_oversized_blocks`
  - Default `split_oversized_blocks`: `frozenset({"paragraph", "blockquote", "html_block"})`
- `Chunk`: final chunk payload with `chunk_id`, `chunk_type`, `body`, `token_count`, `estimated_token_count`, `headings`, `section_level`, `document_title`, `document_path`, `start_line`, `end_line`

## Web API

Implemented in `src/lumberjack/web/`.

- Endpoint: `POST /lumber/api/split`
- Input: form data with `text` (string) or `file` (upload), plus split options
- Split options: `max_tokens`, `merge_below_tokens`, `overlap_tokens`, `merge_small_chunks`, `isolate_front_matter`, `skip_empty_sections`, `recursive_split`, `split_oversized_blocks`, `tokenizer`, `disable_lheading`, `splitter`
- Response: JSON with `document`, `chunk_count`, and `chunks` array
- Valid block types for `split_oversized_blocks`: `paragraph`, `blockquote`, `list`, `table`, `code_block`, `code_fence`, `html_block`
- Server CLI: `lumberjack-serve` with `--host` (default `127.0.0.1`), `--port` (default `8000`), `--reload`
- Thin wrapper around `lumber()` — no splitting logic in the web layer

## Web UI

Implemented in `lumberjack_webui/`.

- React 19 + TypeScript + Vite
- Components: `MarkdownInput` (text/file), `SplitOptions` (basic/advanced), `ChunkList`, `ChunkResult`
- API client: `src/api/split.ts` sends `FormData` to `POST /lumber/api/split`
- Vite dev proxy forwards `/lumber` to `localhost:8000`
- Build output goes to `../src/lumberjack/web/static/` for production serving
- Scripts: `npm run dev`, `npm run build`, `npm run preview`, `npm run lint`

## CLI Behavior

Implemented in `src/lumberjack/main.py`.

- Input is a Markdown file path
- Output formats: `json` or `markdown`
- Tokenizers: `simple`, `tiktoken`
- Parser choices exposed by CLI: `default`, `markdown-it`
- Splitter choices: `recursive`, `section` (CLI default: `recursive`)
- `--retain-headings` is opt-in on the CLI
- `--no-isolate-front-matter` disables front matter isolation
- `--disable-lheading` disables Setext heading parsing
- `--recursive-split` enables block/text fallback for oversized section bodies (effective with `--splitter heading`)
- `--split-oversized-block <kind>` can be repeated; valid kinds: `paragraph`, `blockquote`, `list`, `table`, `code_block`, `code_fence`, `html_block`
- JSON output serializes dataclasses with `dataclasses.asdict`

## Current Parsing Coverage

The parser currently normalizes these block-level structures:

- headings (ATX and Setext)
- paragraphs
- block quotes
- lists and list items
- tables
- fenced code blocks
- indented code blocks
- HTML blocks
- thematic breaks
- link reference definitions
- YAML front matter
- math blocks (`$$...$$`, dollarmath plugin)
- math blocks with equation numbers (dollarmath plugin)
- bracket math blocks (`\[...\]`)
- bracket math blocks with equation numbers (`\[...\](label)`)
- plugin-generated blocks preserved as plugin-specific kinds

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
- math inline (`$...$`, dollarmath plugin)
- bracket math inline (`\(...\)`)
- footnote references and anchors
- plugin-generated inlines preserved with source token metadata

## Splitting Rules

- Whole document is kept as one chunk when it already fits the budget
- `RecursiveMarkdownSplitter` (default): merges adjacent sibling sections when they fit within `max_tokens`
- `SectionMarkdownSplitter`: emits one chunk per heading section direct body; child sections become separate chunks
- Text fallback order is paragraph break -> line break -> sentence -> word -> hard split
- `retain_headings=True` prepends rendered heading breadcrumbs to `Chunk.body`
- `Chunk.body` always includes rendered heading context; shared parent headings are deduplicated when sibling sections are merged into one chunk
- `retain_headings=False` makes `Chunk.body` pure content without any headings; use `render_heading_path(Chunk.headings)` + `Chunk.body` to reconstruct
- Short tails from fragment or text fallback splitting are merged only when they share the same heading path and the estimated merged size still fits within `max_tokens`
- `isolate_front_matter=True` always emits front matter as the first chunk (`chunk_type="front_matter"`)
- `skip_empty_sections=True` discards chunks that contain only a heading with no body content
- Thematic breaks are attached to preceding blocks of kind paragraph, blockquote, html_block, math_block, or math_block_eqno
- `recursive_split=True` enables block/text fallback for oversized section bodies in `SectionMarkdownSplitter`
- Default `split_oversized_blocks` includes `paragraph`, `blockquote`, `html_block`

## Constraints

- Markdown only; no PDF/HTML/DOCX ingestion pipeline is planned here
- Fenced code blocks are preserved intact even when they exceed `max_tokens` (unless `code_block`/`code_fence` is in `split_oversized_blocks`)
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
- web API split with text input, file upload, error handling, and full options

When changing parser or splitter behavior:

1. Update or add fixtures in `tests/fixtures/markdown/`
2. Update implementation in `src/lumberjack/core/` and public API if needed
3. Add or update assertions in `tests/test_parser.py`, `tests/test_splitter.py`, `tests/test_api.py`, and `tests/test_web.py`

After Python code changes:

1. Run `uv run ruff check --fix`
2. Review whether `--unsafe-fixes` is actually needed before using it
3. Run `uv run ruff format`
4. Run the relevant `pytest` scope

## Code Organization

- `src/lumberjack/base/` - protocol interfaces
- `src/lumberjack/core/parser.py` - parser factory and default parser alias
- `src/lumberjack/core/plugins/` - custom markdown-it plugins (brackets_math)
- `src/lumberjack/core/splitter.py` - section/block/text chunking
- `src/lumberjack/core/tokenizers.py` - tokenizer implementations
- `src/lumberjack/core/visitor.py` - lightweight visitor hooks
- `src/lumberjack/api.py` - public Python API
- `src/lumberjack/models.py` - internal data models
- `src/lumberjack/utils.py` - Markdown rendering helpers
- `src/lumberjack/main.py` - CLI orchestration only
- `src/lumberjack/web/` - FastAPI web layer (app, routes, static serving)
- `lumberjack_webui/` - React + TypeScript frontend

## Documentation Notes

Keep docs aligned with the code, especially when any of these change:

- CLI flags or defaults
- parser coverage or built-in plugins
- tokenizer names
- chunk metadata fields
- test commands or dependency groups
- parser implementation strategy
- web API endpoints or parameters
- frontend component structure
- splitter registry names or defaults
