<p align="center">
  <img src="assets/logo.png" alt="lumberjack" width="200">
</p>

<h1 align="center">lumberjack</h1>

<p align="center">
  <strong>Universal, structure-aware document splitting for RAG preprocessing</strong>
</p>

<p align="center">
  Split documents into ready-to-use chunks by structure, not fixed text windows.
  Preserve hierarchy, block integrity, and useful metadata while keeping
  tokenizer work as small as possible through reusable estimates.
</p>

<p align="center">
  <a href="README.zh-CN.md">中文文档</a>
</p>

---

## Why lumberjack?

Most splitters start from plain text windows. That is simple, but it ignores the
meaning already present in real documents: headings, nested sections, tables,
lists, code fences, math blocks, front matter, and source positions. **lumberjack**
parses the input first, builds a shared `DocumentAST`, and then splits that tree
into chunks that are immediately useful for indexing, retrieval, or inspection.

- **Universal input, one output model** — currently supports Markdown, HTML, and DOCX; every parser produces the same `DocumentAST` and `Chunk[]` shape.
- **Ready out of the box** — use the Python API, CLI, Web API, or Web UI without wiring your own parser/splitter stack.
- **Structured splitting** — split along heading sections, nested section trees, and block boundaries before falling back to text-level splitting.
- **Context-preserving chunks** — each chunk carries rendered heading breadcrumbs, source lines, block type, token counts, and document metadata.
- **Block-aware safety** — code blocks, tables, math, front matter, and other special blocks can stay intact, split, or be isolated per kind.
- **Tokenizer-efficient planning** — reusable token estimates, cached counts, and an `ideal_max_tokens_ratio` split budget reduce repeated tokenizer calls while final chunks still report measured token counts.

Core pipeline:

```text
Markdown text → MarkdownItParser → DocumentAST → splitter → Chunk[]
HTML text     → HTMLParser ─────────────────────┤
DOCX binary   → DocxParser ─────────────────────┘
```

### Why not plain text splitting?

Plain text splitters are fine for unstructured notes, but they tend to cut
through semantic boundaries and then force downstream retrieval to guess the
missing context. lumberjack keeps the document structure in the loop: it parses
first, splits by the tree, merges where the budget allows, and only uses
paragraph/line/sentence/word fallback when a block or section is too large.

## Install

### As a library

```bash
pip install lumberjack
```

Optional extras:

```bash
pip install "lumberjack[tokenizers]"   # tiktoken-based model token counting
pip install "lumberjack[docx]"         # DOCX document support
pip install "lumberjack[web]"          # FastAPI web server + UI
pip install "lumberjack[all]"          # everything
```

> [!NOTE]
> Requires Python 3.13+.

### From source (for development)

```bash
git clone https://github.com/tianleG/lumberjack.git
cd lumberjack
uv sync --all-group --all-extra
```

See [Development](#development) for the full development workflow.

## Quick Start

### Python API

```python
from lumberjack import lumber

chunks = lumber(
    "# Introduction\n\nSome content...\n\n## Details\n\nMore content.",
    max_tokens=1200,
)

for chunk in chunks:
    print(f"[{chunk.chunk_id}] tokens={chunk.token_count}")
    print(chunk.body)
    print()
```

### CLI

```bash
lumber document.md --max-tokens 1200
```

### Web UI

```bash
pip install "lumberjack[web]"
lumberjack-serve
```

Open <http://localhost:9612> — paste text or upload a file, configure options, and inspect chunk results visually.

## Usage

### Python API

The public API is a single function — [`lumber()`](src/lumberjack/lumber.py):

```python
from lumberjack import lumber
from lumberjack.core.models import BlockConfig

# Full options
chunks = lumber(
    markdown_text,
    format="markdown",        # "auto" | "markdown" | "html" | "docx"
    document_title="guide.md",
    max_tokens=1200,
    ideal_max_tokens_ratio=0.8,
    merge_below_tokens=50,
    skip_empty_sections=True,
    recursive_split=False,
    tokenizer="simple",        # "simple" | "tiktoken"
    splitter="recursive",      # "recursive" | "section"
)
```

HTML input uses the same splitter pipeline:

```python
chunks = lumber(
    "<h1>Guide</h1><p>Intro</p>",
    format="html",
    max_tokens=1200,
)
```

Each returned `Chunk` carries:

| Field                     | Description                                                              |
| ------------------------- | ------------------------------------------------------------------------ |
| `chunk_id`                | Unique identifier                                                        |
| `chunk_type`              | Origin block type (`"heading"`, `"paragraph"`, `"code_fence"`, ...)     |
| `body`                    | Rendered chunk text with heading breadcrumbs                             |
| `token_count`             | Tokens counted from final body                                           |
| `estimated_token_count`   | Budget estimate used during splitting                                    |
| `headings`                | Tuple of `(level, title)` pairs — the heading breadcrumb                 |
| `section_level`           | Deepest heading level in this chunk                                      |
| `document_title`          | Resolved from front matter or first H1                                   |
| `start_line` / `end_line` | 1-based line range in the source                                         |

#### Per-Block Configuration

Control how individual block kinds are split and merged:

```python
from lumberjack import lumber
from lumberjack.core.models import BlockConfig

chunks = lumber(
    markdown_text,
    block_options={
        # Tables: standalone chunks, never split, 500-token budget
        "table": BlockConfig(isolated=True, split=False, max_tokens=500),
        # Code fences: keep intact even when oversized
        "code_fence": BlockConfig(split=False),
        # Paragraphs: custom budget
        "paragraph": BlockConfig(max_tokens=800),
    },
)
```

`BlockConfig` fields:

- **`isolated`** (`bool`) — emit as standalone chunks, never merge with adjacent content
- **`split`** (`bool`) — allow splitting oversized blocks
- **`max_tokens`** (`int | None`) — per-kind budget override; `None` uses global `max_tokens`

Valid block kinds: `paragraph`, `blockquote`, `list`, `list_item`, `table`, `html_table`, `code_block`, `code_fence`, `html_block`, `front_matter`, `math_block`, `math_block_eqno`.

> [!NOTE]
> **HTML Tables**: HTML tables (`<table>`) are recognized as `html_table` blocks, independent from markdown tables. They preserve their original HTML format and attributes during splitting. Configure with `"html_table": BlockConfig(isolated=True)` to handle separately from markdown tables.

#### Custom Parser with Plugins

```python
from mdit_py_plugins.tasklists import tasklists_plugin
from lumberjack.core.parsers.markdown.parser import MarkdownItParser
from lumberjack import lumber

chunks = lumber(
    markdown_text,
    parser=MarkdownItParser(plugins=(tasklists_plugin,)),
)
```

### CLI

```bash
lumber <input> [options]
```

| Option                     | Default     | Description                                      |
| -------------------------- | ----------- | ------------------------------------------------ |
| `input`                    | —           | Path to a Markdown (.md), HTML (.html), or DOCX (.docx) file |
| `--input-format`           | `auto`      | `auto`, `markdown`, `html`, or `docx`            |
| `-o`, `--output`           | stdout      | Write output to file                             |
| `--max-tokens`             | `1200`      | Maximum chunk token budget                       |
| `--ideal-max-tokens-ratio` | `0.8`       | Preferred split budget ratio                     |
| `--merge-below-tokens`     | `50`        | Soft threshold for small-chunk merging           |
| `--tokenizer`              | `simple`    | `simple` or `tiktoken`                           |
| `--splitter`               | `recursive` | `recursive` or `section`                         |
| `--recursive-split`        | off         | Enable block/text fallback for section splitter  |
| `--block-config`           | —           | Per-block-kind config (repeatable)               |

`--block-config` syntax: `KIND[:isolated][:nosplit][:TOKENS]`

```bash
# Isolate tables, disable splitting, 500-token budget
lumber doc.md --block-config table:isolated:nosplit:500

# Keep code fences intact
lumber doc.md --block-config code_fence:nosplit

# Multiple block configs
lumber doc.md --block-config table:isolated --block-config code_fence:nosplit
```

**JSON output** includes `document`, `chunk_count`, and a `chunks` array with full metadata.

### Web API

Start the server:

```bash
lumberjack-serve --host 127.0.0.1 --port 9612
```

#### `POST /lumber/api/split/text`

```bash
curl -X POST http://localhost:9612/lumber/api/split/text \
  -H "Content-Type: application/json" \
  -d '{"text": "# Hello\n\nWorld", "input_format": "markdown", "max_tokens": 500}'
```

#### `POST /lumber/api/split/file`

```bash
curl -X POST http://localhost:9612/lumber/api/split/file \
  -F "file=@guide.md" \
  -F "input_format=auto" \
  -F "max_tokens=500" \
  -F "splitter=section"
```

#### Web API Options

Both endpoints accept the same options:

| Field | Type | Default | Description |
| --- | --- | --- | --- |
| `input_format` | string | `"markdown"` for text, `"auto"` for file upload | `auto`, `markdown`, `html`, or `docx` |
| `max_tokens` | int | `1200` | Maximum chunk token budget |
| `ideal_max_tokens_ratio` | float | `0.8` | Preferred split budget ratio |
| `merge_below_tokens` | int | `50` | Soft merge threshold |
| `skip_empty_sections` | bool | `true` | Discard heading-only chunks |
| `recursive_split` | bool | `false` | Block/text fallback for section splitter |
| `block_configs` | object | `null` | Per-block-kind config |
| `tokenizer` | string | `"simple"` | `simple` or `tiktoken` |
| `splitter` | string | `"recursive"` | `recursive` or `section` |

#### Response

```json
{
  "document": "guide.md",
  "chunk_count": 1,
  "chunks": [
    {
      "chunk_id": "chunk-001",
      "chunk_type": "heading",
      "body": "# Hello\n\nWorld",
      "token_count": 8,
      "estimated_token_count": 8,
      "headings": [[1, "Hello"]],
      "section_level": 1,
      "document_title": "guide.md",
      "document_path": null,
      "start_line": 1,
      "end_line": 3
    }
  ]
}
```

### Docker

```bash
cp .env.example .env
docker compose up --build
```

Open <http://localhost:9612>.

## Splitting Strategies

| Strategy | Registry Name | Behavior |
| --- | --- | --- |
| **Recursive** | `recursive` (default) | Structure-first, budget-aware. Merges adjacent sibling sections when they fit. |
| **Section** | `section` | One chunk per heading section's direct body. Child sections are separate chunks. |

Recursive splitting order:

1. Keep the whole document as one chunk if it fits
2. Split by heading sections
3. Split oversized sections by block boundaries
4. Fall back to paragraph → line → sentence → word → hard split

> [!IMPORTANT]
> Code blocks are preserved intact by default even when they exceed `max_tokens`. Use `BlockConfig(split=True)` to allow splitting specific block kinds.

## Parsing Coverage

**Block-level structures:**

Markdown: ATX headings · Setext headings · Paragraphs · Block quotes · Ordered/unordered lists · Tables · Fenced code · Indented code · HTML blocks · Link reference definitions · YAML front matter · Math blocks (`$$...$$`) · Bracket math blocks (`\[...\]`) · Equation-numbered math · Plugin-generated blocks

HTML: Headings · Paragraphs · Block quotes · Lists · Code blocks · Tables as `html_table` · Document title and meta tags

**Inline structures** (in headings and paragraphs):

Text · Links · Images · Autolinks · Code spans · Emphasis · Strong emphasis · Strikethrough · Inline HTML · Line breaks · Inline math (`$...$`) · Bracket inline math (`\(...\)`) · Footnote references · Plugin-generated inlines

**Additional preservation:**

- Heading title inlines
- Reference link definitions in `DocumentAST.reference_definitions`
- Source line ranges for headings and blocks

## Architecture

```text
src/lumberjack/
├── __init__.py              # Public API re-exports
├── lumber.py                # Public lumber() implementation
├── cli.py                   # CLI entry point (lumber)
├── core/
│   ├── models.py            # Data models (Chunk, BlockConfig, SplitOptions, ...)
│   ├── protocols.py         # Protocol interfaces
│   ├── tokenizers.py        # Simple character & tiktoken tokenizers
│   ├── splitter.py          # Recursive & section splitters (operate on DocumentAST)
│   ├── block.py             # BlockSplitter for oversized blocks + block-config parsing
│   ├── utils.py             # Markdown rendering helpers
│   ├── visitor.py           # AstVisitor for AST traversal
│   └── parsers/             # Format-specific parsers: raw input -> DocumentAST
│       ├── markdown/
│       │   ├── parser.py    # MarkdownItParser (markdown-it-py backend)
│       │   └── plugins/     # Custom markdown-it plugins (bracket math)
│       ├── html/
│       │   ├── parser.py    # HTMLParser (stdlib html.parser backend)
│       │   └── table_parser.py  # HTML table extraction and row parsing
│       └── docx/
│           └── parser.py    # DocxParser (python-docx backend)
└── web/
    ├── app.py               # FastAPI application
    ├── routes.py            # API endpoints
    └── __main__.py          # Server entry point (lumberjack-serve)
```

## Development

This project uses [uv](https://docs.astral.sh/uv/) for dependency management.

```bash
# Clone and install all dependencies
git clone https://github.com/tianleG/lumberjack.git
cd lumberjack
uv sync --group dev --group test --extra tokenizers --extra docx

# Run tests
uv run pytest

# Lint and format (ruff)
uv run ruff check --fix
uv run ruff format

# Type check (ty)
uv run ty check
```

> [!TIP]
> This project uses [ruff](https://docs.astral.sh/ruff/) for linting & formatting, and [ty](https://docs.astral.sh/ty/) for type checking.

## License

[MIT](LICENSE)
