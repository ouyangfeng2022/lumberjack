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

The shared AST is format-neutral: `DocumentInline`, `DocumentBlock`, and
`SectionNode` hold canonical Markdown-like rendered text for splitting.
Markdown/HTML keep their original text in `DocumentAST.source`; binary formats
may leave it empty or provide normalized source text. A block's rendered text is not guaranteed
to be a byte-for-byte source slice. See the
[public contract](docs/reference/public-contract.md) for the precise semantics.

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
pip install "lumberjack[tokenizers]"   # tiktoken / transformers token counting
pip install "lumberjack[docx]"         # DOCX document support
pip install "lumberjack[web]"          # FastAPI web server + UI
pip install "lumberjack[all]"          # everything
```

To pin a stable release:

```bash
pip install "lumberjack==<version>"
```

> [!NOTE]
> Requires Python 3.10+.

### From source (for development)

```bash
git clone https://github.com/ouyangfeng2022/lumberjack.git
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

The default public API is a single function — [`lumber()`](src/lumberjack/lumber.py).
It is the ready-to-use pipeline and only accepts string selectors for built-in
tokenizers and splitters:

```python
from lumberjack import lumber

# Full options
chunks = lumber(
    markdown_text,
    format="markdown",        # "auto" | "markdown" | "html" | "docx"
    document_title="guide.md",
    max_tokens=1200,
    ideal_max_tokens_ratio=0.8,
    merge_below_ratio=0.125,
    skip_empty_sections=True,
    render_headings=True,      # False: drop ancestor heading breadcrumb from body
    tokenizer="approx",        # "approx" | "tiktoken" | "transformers"
    splitter="sibling",        # "sibling" | "subtree" | "section"
)
```

Counting strategy is a property of the splitter class, not the tokenizer.
The default `sibling`, `subtree`, and `section` splitters are **exact**: every budget
decision fully recounts the rendered candidate text (`token_count ==
estimated_token_count`). The `incremental-sibling`,
`incremental-subtree`, and `incremental-section` variants pre-measure the tree once and use a running
additive estimate with an 8-char separator-delta window for joins — faster
for heavy tokenizers, at the cost of `estimated_token_count` diverging
slightly from the authoritative `token_count` (the full recount at
finalization). Any tokenizer works with any splitter.

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
| `token_count`             | Tokens counted from the rendered body (full recount)                     |
| `estimated_token_count`   | Token estimate used during splitting                                     |
| `headings`                | Tuple of `(level, title)` pairs — the ancestor heading breadcrumb        |
| `section_level`           | Deepest heading level in this chunk                                      |
| `document_title`          | Resolved from front matter or first H1                                   |
| `start_line` / `end_line` | 1-based line range in the source                                         |

#### Per-Block Configuration

Control how individual block kinds are split and merged:

```python
from lumberjack import lumber
from lumberjack.core.models import BaseParams, TableBlockParams

chunks = lumber(
    markdown_text,
    block_options={
        # Tables: standalone chunks, 500-token budget, do not repeat headers after split
        "table": TableBlockParams(
            isolated=True,
            max_tokens=500,
            repeat_header=False,
        ),
        # Code fences: keep intact even when oversized
        "code_fence": BaseParams(split=False),
        # Paragraphs: custom budget
        "paragraph": BaseParams(max_tokens=800),
    },
)
```

`BaseParams` fields:

- **`isolated`** (`bool`) — emit as standalone chunks, never merge with adjacent content
- **`split`** (`bool`) — allow splitting oversized blocks
- **`max_tokens`** (`int | None`) — per-kind budget override; `None` uses global `max_tokens`
- Block-specific params inherit these common fields. `TableBlockParams` adds **`repeat_header`** (`bool`) for `table` and `html_table`; other kinds reject table-specific fields until they define their own params type.

Valid block kinds: `paragraph`, `blockquote`, `list`, `list_item`, `table`, `html_table`, `code_block`, `code_fence`, `html_block`, `front_matter`, `math_block`, `math_block_eqno`.

> [!NOTE]
> **HTML Tables**: HTML tables (`<table>`) are recognized as `html_table` blocks, independent from markdown tables. They preserve their original HTML format and attributes during splitting. Configure with `"html_table": TableBlockParams(isolated=True)` to handle separately from markdown tables.

#### Custom Parser, Tokenizer, or Splitter

`lumber()` intentionally stays small and general-purpose. If you need a custom
parser, tokenizer, or splitter, compose the lower-level pieces directly: parse
once, then split once.

```python
from mdit_py_plugins.tasklists import tasklists_plugin
from lumberjack.core.models import SplitOptions
from lumberjack.core.options import resolve_block_options
from lumberjack.core.parser.markdown.parser import MarkdownItParser
from lumberjack.core.splitter import SiblingSplitter
from lumberjack.core.tokenizers import TiktokenTokenizer

parser = MarkdownItParser(plugins=(tasklists_plugin,))
tokenizer = TiktokenTokenizer(model="gpt-4o-mini")

document = parser.parse(markdown_text, document_title="guide.md")
options = SplitOptions(
    max_tokens=1200,
    block_options=resolve_block_options(parser.block_kinds, None),
)
splitter = SiblingSplitter(tokenizer=tokenizer, options=options)

chunks = splitter.split(document)
```

Custom components should follow the protocols in
[`lumberjack.core.protocols`](src/lumberjack/core/protocols.py). They are not
passed through `lumber()`; use the `parse -> split` pipeline directly instead.

#### Markdown Parser Plugins

`MarkdownItParser` accepts regular `markdown-it-py` plugins through
`plugins`. If a plugin only changes existing Markdown structures, such as task
lists rendering as list items with inline HTML checkboxes, no extra setup is
needed:

```python
from mdit_py_plugins.tasklists import tasklists_plugin
from lumberjack.core.parser.markdown import MarkdownItParser

parser = MarkdownItParser(plugins=(tasklists_plugin,))
document = parser.parse("- [x] done", document_title="tasks.md")
```

When a plugin emits new block token types, declare how those token types map to
lumberjack block kinds with `MarkdownBlockSpec`. The parser merges those custom
kinds into `parser.block_kinds`, which is the set used by
`resolve_block_options()` and splitter validation.

This complete example uses `mdit_py_plugins.container.container_plugin` to parse
custom callout containers as a first-class `callout` block kind, then isolates
that block kind during splitting:

```python
from mdit_py_plugins.container import container_plugin

from lumberjack.core.models import BaseParams, DocumentBlock, SplitOptions
from lumberjack.core.options import resolve_block_options
from lumberjack.core.parser.markdown import MarkdownBlockContext, MarkdownBlockSpec
from lumberjack.core.parser.markdown import MarkdownItParser
from lumberjack.core.splitter import SiblingSplitter
from lumberjack.core.tokenizers import SimpleCharTokenizer


def callout_block(context: MarkdownBlockContext) -> tuple[DocumentBlock | None, int]:
    close_index = context.parser.find_matching_close(context.tokens, context.index)
    children = context.parser.parse_child_blocks(
        context.tokens,
        context.index + 1,
        close_index,
        context.source_lines,
    )
    body = "\n\n".join(child.text for child in children if child.text)
    return (
        DocumentBlock(
            kind="callout",
            text=body,
            start_line=context.token.map[0] + 1 if context.token.map else None,
            end_line=context.token.map[1] if context.token.map else None,
            children=children,
            attrs={
                "source_token_type": context.token.type,
                "info": context.token.info.strip(),
            },
        ),
        close_index + 1,
    )


parser = MarkdownItParser(
    plugins=(lambda md: container_plugin(md, name="callout"),),
    block_specs=(
        MarkdownBlockSpec(
            kind="callout",
            token_types=("container_callout_open",),
            handler=callout_block,
        ),
    ),
)

markdown_text = """# Guide

::: callout note
Remember to configure custom block kinds before splitting.
:::
"""

document = parser.parse(markdown_text, document_title="guide.md")
options = SplitOptions(
    max_tokens=1200,
    block_options=resolve_block_options(
        parser.block_kinds,
        {"callout": BaseParams(isolated=True, max_tokens=400)},
    ),
)
chunks = SiblingSplitter(
    tokenizer=SimpleCharTokenizer(),
    options=options,
).split(document)
```

`MarkdownBlockSpec` rules:

- `kind` is normalized to lowercase and becomes the `DocumentBlock.kind`.
- `token_types` must be an iterable of custom markdown-it token type strings,
  for example `("container_callout_open",)`.
- `handler` is optional. Without one, lumberjack captures the source slice and
  recursively parses child block tokens for container-style tokens.
- A handler receives `MarkdownBlockContext` and returns `(block, next_index)`.
  Return `None` for the block when the token should be skipped.
- Handler blocks must use the declared `kind`; returning another kind raises
  `ValueError`.
- Built-in Markdown token types such as `paragraph_open`, `fence`,
  `table_open`, and `html_block` are handled internally and cannot be remapped
  with `MarkdownBlockSpec`.

Use `parser.block_kinds`, not `MarkdownItParser.default_block_kinds`, when
validating options for a parser with plugins. `default_block_kinds` only
contains the built-in Markdown kinds; the instance `block_kinds` also includes
plugin-provided kinds such as `callout`.

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
| `--merge-below-ratio`      | `0.125`     | Tail-fragment merge threshold as fraction of max-tokens (0 disables) |
| `--tokenizer`              | `approx`    | `approx`, `tiktoken`, or `transformers` |
| `--splitter`               | `sibling` | `sibling`, `subtree`, `section`, `exact-sibling`, `incremental-sibling`, `exact-subtree`, `incremental-subtree`, `exact-section`, `incremental-section` |
| `--no-render-headings`     | off         | Omit ancestor heading breadcrumb from `body` (see [render_headings](#rendering-headings-render_headings)) |
| `--max-heading-level`      | —           | Maximum heading level to keep as chunk section context; deeper headings render as body text |
| `--block-config`           | —           | Per-block-kind config (repeatable)               |
| `--block-config-json`      | —           | Structured per-block-kind JSON config            |

`--block-config` syntax: `KIND[:isolated][:nosplit][:TOKENS]`

```bash
# Isolate tables, disable splitting, 500-token budget
lumber doc.md --block-config table:isolated:nosplit:500

# Keep code fences intact
lumber doc.md --block-config code_fence:nosplit

# Multiple block configs
lumber doc.md --block-config table:isolated --block-config code_fence:nosplit

# Table-specific params: split tables without repeating header rows after the first piece
lumber doc.md --block-config-json '{"table":{"repeat_header":false}}'
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
| `merge_below_ratio` | float | `0.125` | Tail-fragment merge threshold as fraction of max_tokens (0 disables) |
| `skip_empty_sections` | bool | `true` | Discard heading-only chunks |
| `render_headings` | bool | `true` | Omit ancestor heading breadcrumb from `body` when `false` (see [render_headings](#rendering-headings-render_headings)) |
| `max_heading_level` | int or null | `null` | Maximum heading level to keep as chunk section context; deeper headings render as body text |
| `block_configs` | object | `null` | Per-block-kind config |
| `tokenizer` | string | `"approx"` | `approx`, `tiktoken`, or `transformers` |
| `splitter` | string | `"sibling"` | `sibling`, `subtree`, `section`, `exact-sibling`, `incremental-sibling`, `exact-subtree`, `incremental-subtree`, `exact-section`, `incremental-section` |

Example `block_configs` payload:

```json
{
  "table": {
    "isolated": true,
    "max_tokens": 500,
    "repeat_header": false
  },
  "html_table": {
    "repeat_header": false
  }
}
```

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
      "headings": [],
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
| **Sibling** | `sibling` (default) | Greedily packs a section body and fitting sibling subtrees within the budget. |
| **Incremental Sibling** | `incremental-sibling` | Same topology as `Sibling` with the additive incremental estimate path. |
| **Subtree** | `subtree` | Subtree-first: collapses an entire subtree into one chunk when it fits the budget and has no standalone block; otherwise one chunk per heading section (with tail-fragment merging). |
| **Section** | `section` | Per-heading section splitter: always one chunk per heading section's direct body, no subtree-collapse, no tail-fragment merging. |
| **Incremental Subtree** | `incremental-subtree` | Same topology as `Subtree` with the additive incremental estimate path. |
| **Incremental Section** | `incremental-section` | Same as `Section` with the additive incremental estimate path. |

Sibling-packing split order:

1. Keep the whole document as one chunk if it fits
2. Split by heading sections
3. Split oversized sections by block boundaries
4. Fall back to paragraph → line → sentence → word → hard split

> [!IMPORTANT]
> Code blocks are preserved intact by default even when they exceed `max_tokens`. Use `BaseParams(split=True)` to allow splitting specific block kinds.

### Rendering Headings (`render_headings`)

By default each chunk's rendered `body` starts with its ancestor heading
breadcrumb, followed by the chunk's own heading when it has one (for example,
an H2 leaf renders `# Title\n\n## Section`). `Chunk.headings` stores only the
ancestor breadcrumb. Set `render_headings=False` to omit the ancestor
breadcrumb from `body`; the chunk's own heading and internal relative headings
still render. All splitter topologies are render-aware:

| Splitter | Body behavior | Budget behavior |
| --- | --- | --- |
| **Section** | Ancestor heading breadcrumb omitted; the section's own title still renders | **Render-aware**: the budget previously reserved for ancestor headings is reclaimed for rendered content, so `max_tokens` faithfully bounds the rendered body (`token_count` measures the rendered body tokens). |
| **Subtree** | Ancestor heading breadcrumb omitted; the selected subtree's own and internal relative headings still render | **Render-aware**: subtree-fit decisions count only headings that remain in the rendered body. |
| **Sibling** (default) | Ancestor heading breadcrumb omitted; the chunk's own title and *internal* relative headings (e.g. sibling `###` titles inside a merged chunk) still render | **Render-aware**: the split budget grows only by hidden ancestor headings. The split plan (chunk count, boundaries) may differ from `render_headings=True` when chunks have ancestors. |

> [!NOTE]
> All splitter topologies keep heading tokens in the draft-level accounting so that
> merge arithmetic stays self-consistent — when merging two chunks changes
> their shared ancestor prefix, displaced heading tokens fall back into the body
> as own or internal relative headings that still render. The split-budget decision and
> the running `estimated_token_count` are render-aware, so the estimate tracks
> the actually-rendered `body` (it may differ from `token_count` by a token or
> two due to the separator approximation).

```python
# All splitter topologies use render-aware budgets
lumber(doc, splitter="section", render_headings=False, max_tokens=1000)
lumber(doc, splitter="subtree", render_headings=False, max_tokens=1000)
lumber(doc, splitter="sibling", render_headings=False, max_tokens=1000)
```

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
├── formats.py               # Input format detection and source reading helpers
├── lumber.py                # Public lumber() implementation
├── cli.py                   # CLI entry point (lumber)
├── core/
│   ├── models.py            # Data models (Chunk, BaseParams, SplitOptions, ...)
│   ├── protocols.py         # Protocol interfaces
│   ├── tokenizers.py        # Approximate, tiktoken, and transformers tokenizers
│   ├── block.py             # BlockSplitter for oversized blocks + block-config parsing
│   ├── options.py           # Split option and block config helpers
│   ├── utils.py             # Markdown rendering helpers
│   ├── visitor.py           # AstVisitor for AST traversal
│   ├── splitter/           # Sibling, subtree & section splitters
│   │   ├── base.py          # Shared splitter helpers
│   │   ├── sibling.py       # SiblingSplitter
│   │   ├── subtree.py       # SubtreeSplitter
│   │   ├── section.py       # SectionSplitter
│   │   └── __init__.py      # Splitter registry/factory
│   └── parser/             # Format-specific parsers: raw input -> DocumentAST
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
git clone https://github.com/ouyangfeng2022/lumberjack.git
cd lumberjack
uv sync --group dev --group test --extra tokenizers --extra docx --extra web

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

## Contributing

Contributions are welcome! Whether it's a bug report, a feature idea, or a pull request — we appreciate your help.

- **Bugs & features**: open an [issue](https://github.com/ouyangfeng2022/lumberjack/issues/new/choose) using the bug report or feature request template.
- **Code**: read [CONTRIBUTING.md](CONTRIBUTING.md) for setup, coding standards, and the pull request workflow. Every PR needs to pass CI and get one approval before merging.
- **Questions & discussion**: open an [issue](https://github.com/ouyangfeng2022/lumberjack/issues/new/choose) while Discussions are not enabled.

Please follow our [Code of Conduct](CODE_OF_CONDUCT.md) in all interactions.

## License

[MIT](LICENSE)
