# lumberjack

`lumberjack` is an AST-driven Markdown splitter for long-document retrieval and RAG preprocessing.
It parses Markdown into a section-aware document tree first, then splits by structure instead of by
plain character windows.

The current implementation targets [CommonMark 0.31.2](https://spec.commonmark.org/0.31.2/).
The parser follows CommonMark parsing rules via a normalized CommonMark AST pipeline, so links,
images, emphasis, code, block quotes, lists, thematic breaks, HTML blocks, reference links, and
headings are all preserved in the internal model.

## Install

For development:

```bash
uv sync --group test --extra tokenizers
```

## CLI

```bash
lumberjack path/to/file.md --max-tokens 1200 --min-tokens 200 --format json
```

## Project Goals

`lumberjack` is intentionally focused on Markdown only.

The core pipeline is:

```text
Markdown text -> Markdown parser -> DocumentAST -> Markdown splitter -> Chunk[]
```

Key design constraints:

- Markdown only. No PDF, HTML, or DOCX ingestion is planned in the core package.
- `demo.py` is reference material, not production code.
- Code fences are never split across chunks.
- Business logic stays in `src/lumberjack/core/`; `main.py` is CLI orchestration only.

## Parser

The parser is now a single built-in CommonMark parser.
It builds lumberjack's internal AST from a CommonMark parse tree and preserves richer syntax
metadata for downstream tooling.

### CommonMark coverage

Block-level structures currently normalized into the internal AST:

- ATX headings
- Paragraphs
- Block quotes
- Ordered and unordered lists
- Fenced code blocks
- Indented code blocks
- HTML blocks
- Thematic breaks
- Link reference definitions

Inline structures currently captured inside headings and paragraphs:

- Text
- Links
- Images
- Autolinks
- Code spans
- Emphasis
- Strong emphasis
- Inline HTML
- Soft and hard line breaks

### Internal AST shape

The parser produces a `DocumentAST` with:

- A heading tree (`SectionNode`)
- Section-local blocks (`MarkdownBlock`)
- Inline syntax nodes (`MarkdownInline`) for heading content and paragraph content
- Reference link definitions in `DocumentAST.reference_definitions`

This richer model lets the splitter keep working with rendered Markdown text while exposing more
semantic detail for future metadata or downstream transformations.

## Splitting Strategy

Splitting still follows the same three-tier fallback:

1. Split by heading sections.
2. If a section is too large, split by block boundaries.
3. If a block is still too large, degrade to paragraph / line / sentence / word / hard split.

Important behavior:

- Heading context is preserved in chunks.
- Shared parent headings are deduplicated when sibling sections are merged.
- Oversized code fences stay intact even if they exceed the token budget.

## Usage From Python

```python
from lumberjack import parse_markdown, split_markdown_text

document = parse_markdown(markdown_text, document_title="guide.md")
chunks = split_markdown_text(markdown_text, document_title="guide.md", max_tokens=1200)
```

## Repository Layout

```text
src/lumberjack/base/      Protocol interfaces
src/lumberjack/core/      Parser, splitter, tokenizer implementations
src/lumberjack/models.py  Internal data models
src/lumberjack/main.py    CLI entrypoint
tests/                    Parser, splitter, and API tests
docs/                     Architecture and development notes
```

## Testing

Run the full test suite:

```bash
uv run pytest
```

Run individual files:

```bash
uv run pytest tests/test_parser.py
uv run pytest tests/test_splitter.py
```

## Current Limits

`lumberjack` now follows CommonMark for parsing, but the product goal is still semantic splitting,
not lossless Markdown round-tripping.

That means:

- The internal AST is richer than before, but still normalized for splitting use cases.
- Some rendered block text may be normalized rather than byte-for-byte identical to the source.
- GFM-only extensions such as tables are not part of the CommonMark target unless added separately.

## Roadmap

- M1: Markdown AST splitting
- M2: Chunk metadata such as line ranges and section paths
- M3: Additional downstream AST consumers and metadata features
- M4: Production hardening, golden tests, and benchmarks
