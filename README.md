<p align="center">
  <img src="assets/logo.png" alt="lumberjack" width="200">
</p>

<h1 align="center">lumberjack</h1>

<p align="center">
  <strong>Structure-aware Markdown splitter for RAG preprocessing</strong>
</p>

<p align="center">
  Split Markdown by document structure, not fixed text windows.
  Preserves heading hierarchy, block integrity, and inline semantics.
</p>

<p align="center">
  <a href="README.zh-CN.md">中文文档</a>
</p>

---

## Why lumberjack?

Naive text splitters break Markdown at arbitrary character boundaries — slicing through code blocks, splitting tables mid-row, and losing heading context. **lumberjack** treats your document as a tree, not a string:

- **Structure-first splitting** — breaks along heading sections and block boundaries
- **Budget-aware merging** — adjacent sibling sections merge when they fit
- **Block integrity** — code blocks, tables, and math stay intact by default
- **Heading context preserved** — every chunk carries its full heading breadcrumb
- **Multiple interfaces** — Python API, CLI, and Web UI out of the box

Core pipeline:

```text
Markdown text → parser tokens → DocumentAST → splitter → Chunk[]
```

## Install

```bash
pip install lumberjack
```

Optional extras:

```bash
pip install "lumberjack[tokenizers]"   # tiktoken-based model token counting
pip install "lumberjack[web]"          # FastAPI web server + UI
pip install "lumberjack[all]"          # everything
```

> [!NOTE]
> Requires Python 3.13+.

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
lumber document.md --max-tokens 1200 --format json
```

### Web UI

```bash
pip install "lumberjack[web]"
lumberjack-serve
```

Open <http://localhost:9612> — paste text or upload a `.md` file, configure options, and inspect chunk results visually.

## Usage

### Python API

The public API is a single function — [`lumber()`](src/lumberjack/__init__.py):

```python
from lumberjack import lumber
from lumberjack.core.models import BlockConfig

# Full options
chunks = lumber(
    markdown_text,
    document_title="guide.md",
    max_tokens=1200,
    ideal_max_tokens_ratio=0.8,
    merge_below_tokens=50,
    overlap_tokens=0,
    merge_small_chunks=True,
    skip_empty_sections=True,
    recursive_split=False,
    tokenizer="simple",        # "simple" | "tiktoken"
    parser="default",          # "default" | "markdown-it"
    splitter="recursive",      # "recursive" | "section"
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

Valid block kinds: `paragraph`, `blockquote`, `list`, `list_item`, `table`, `code_block`, `code_fence`, `html_block`, `front_matter`, `math_block`, `math_block_eqno`.

> [!TIP]
> `block_options` also accepts plain dicts: `{"table": {"isolated": True, "split": False}}`.

#### Custom Parser with Plugins

```python
from mdit_py_plugins.tasklists import tasklists_plugin
from lumberjack.core.parser import MarkdownItParser
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
| `input`                    | —           | Path to a Markdown file                          |
| `-o`, `--output`           | stdout      | Write output to file                             |
| `-f`, `--format`           | `json`      | Output format: `json` or `markdown`              |
| `--max-tokens`             | `1200`      | Maximum chunk token budget                       |
| `--ideal-max-tokens-ratio` | `0.8`       | Preferred split budget ratio                     |
| `--merge-below-tokens`     | `50`        | Soft threshold for small-chunk merging           |
| `--overlap-tokens`         | `0`         | Token overlap for text fallback splits           |
| `--tokenizer`              | `simple`    | `simple` or `tiktoken`                           |
| `--splitter`               | `recursive` | `recursive` or `section`                         |
| `--recursive-split`        | off         | Enable block/text fallback for section splitter  |
| `--block-config`           | —           | Per-block-kind config (repeatable)               |
| `--disable-lheading`       | off         | Disable Setext heading parsing                   |

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

**Markdown output** renders each chunk separated by HTML comments:

```markdown
<!-- chunk 1 tokens=42 -->
## Getting Started

Install with pip...

<!-- chunk 2 tokens=87 -->
## Usage

...
```

### Web API

Start the server:

```bash
lumberjack-serve --host 127.0.0.1 --port 9612
```

#### `POST /lumber/api/split/text`

```bash
curl -X POST http://localhost:9612/lumber/api/split/text \
  -H "Content-Type: application/json" \
  -d '{"text": "# Hello\n\nWorld", "max_tokens": 500}'
```

#### `POST /lumber/api/split/file`

```bash
curl -X POST http://localhost:9612/lumber/api/split/file \
  -F "file=@guide.md" \
  -F "max_tokens=500" \
  -F "splitter=section"
```

#### Web API Options

Both endpoints accept the same options:

| Field                     | Type    | Default      | Description                               |
| ------------------------ | ------- | ------------ | ----------------------------------------- |
| `max_tokens`             | int     | `1200`       | Maximum chunk token budget                |
| `ideal_max_tokens_ratio` | float   | `0.8`        | Preferred split budget ratio              |
| `merge_below_tokens`     | int     | `50`         | Soft merge threshold                      |
| `overlap_tokens`         | int     | `0`          | Token overlap for text fallback           |
| `merge_small_chunks`     | bool    | `true`       | Merge adjacent small chunks               |
| `skip_empty_sections`    | bool    | `true`       | Discard heading-only chunks               |
| `recursive_split`        | bool    | `false`      | Block/text fallback for section splitter  |
| `block_configs`          | object  | `null`       | Per-block-kind config                     |
| `disable_lheading`       | bool    | `false`      | Disable Setext headings                   |
| `tokenizer`              | string  | `"simple"`   | `simple` or `tiktoken`                    |
| `splitter`               | string  | `"recursive"` | `recursive` or `section`                 |

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

| Strategy     | Registry Name        | Behavior                                                                       |
| ------------ | -------------------- | ------------------------------------------------------------------------------ |
| **Recursive** | `recursive` (default) | Structure-first, budget-aware. Merges adjacent sibling sections when they fit. |
| **Section**  | `section`            | One chunk per heading section's direct body. Child sections are separate chunks. |

Recursive splitting order:

1. Keep the whole document as one chunk if it fits
2. Split by heading sections
3. Split oversized sections by block boundaries
4. Fall back to paragraph → line → sentence → word → hard split

> [!IMPORTANT]
> Code blocks are preserved intact by default even when they exceed `max_tokens`. Use `BlockConfig(split=True)` to allow splitting specific block kinds.

## Parsing Coverage

**Block-level structures:**

ATX headings · Setext headings · Paragraphs · Block quotes · Ordered/unordered lists · Tables · Fenced code · Indented code · HTML blocks · Link reference definitions · YAML front matter · Math blocks (`$$...$$`) · Bracket math blocks (`\[...\]`) · Equation-numbered math · Plugin-generated blocks

**Inline structures** (in headings and paragraphs):

Text · Links · Images · Autolinks · Code spans · Emphasis · Strong emphasis · Strikethrough · Inline HTML · Line breaks · Inline math (`$...$`) · Bracket inline math (`\(...\)`) · Footnote references · Plugin-generated inlines

**Additional preservation:**

- Heading title inlines
- Reference link definitions in `DocumentAST.reference_definitions`
- Source line ranges for headings and blocks

## Architecture

```text
src/lumberjack/
├── __init__.py              # Public API (lumber function)
├── cli.py                   # CLI entry point (lumber)
├── core/
│   ├── parser.py            # Markdown parser (markdown-it-py backend)
│   ├── splitter.py          # Recursive & section splitters
│   ├── tokenizers.py        # Simple character & tiktoken tokenizers
│   ├── models.py            # Data models (Chunk, BlockConfig, SplitOptions, ...)
│   ├── protocols.py         # Protocol interfaces
│   ├── block_config.py      # Block config parsing helpers
│   ├── plugins/             # Custom markdown-it plugins (bracket math)
│   ├── utils.py             # Markdown rendering helpers
│   └── visitor.py           # Visitor pattern hooks
└── web/
    ├── app.py               # FastAPI application
    ├── routes.py            # API endpoints
    └── __main__.py          # Server entry point (lumberjack-serve)
```

## Development

```bash
# Install with dev, test, and tokenizer dependencies
uv sync --group dev --group test --extra tokenizers

# Run tests
uv run pytest

# Lint and format
uv run ruff check --fix
uv run ruff format
```

## License

[MIT](LICENSE)
