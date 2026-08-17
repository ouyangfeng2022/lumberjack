<p align="center">
  <img src="assets/lumberjack-logo.svg" width="160" alt="Lumberjack logo: an axe, document, trees, and a tree ring" />
</p>

# Lumberjack

[![PyPI](https://img.shields.io/pypi/v/lumberjack.svg)](https://pypi.org/project/lumberjack/)
[![Python](https://img.shields.io/pypi/pyversions/lumberjack.svg)](https://pypi.org/project/lumberjack/)
[![CI](https://github.com/ouyangfeng2022/lumberjack/actions/workflows/ci.yml/badge.svg)](https://github.com/ouyangfeng2022/lumberjack/actions/workflows/ci.yml)

**Turn long, structured documents into retrieval-ready chunks without losing
their context.**

Lumberjack is a Python library and CLI for preparing documentation, reports,
and knowledge-base content for RAG. It reads a document's structure, keeps
headings with the text they introduce, respects tables and code blocks, and
splits only when a chunk exceeds its token budget.

[中文说明](README.zh-CN.md)

## Why Lumberjack?

Plain-text splitters cut at character or token boundaries. That can detach an
answer from its section title, split a table in the middle, or join unrelated
topics merely because they happen to be adjacent.

Lumberjack works from a normalized document tree instead:

- **Keep useful context.** Chunks carry their heading path and source metadata.
- **Honor document structure.** Headings, paragraphs, lists, tables, and fenced
  code are handled as document blocks rather than as unstructured text.
- **Use the budget efficiently.** The default splitter uses inexpensive running
  estimates while packing sections, then produces an authoritative final token
  count.
- **Choose the shape of a chunk.** Pack sibling sections, retain whole
  subtrees, or split direct section bodies—without changing the input format.

Markdown, HTML, and DOCX are currently supported.

## Install

```bash
pip install lumberjack

# Optional exact tokenizers, DOCX support, and the Web API
pip install "lumberjack[tokenizers,docx,web]"
```

Lumberjack requires Python 3.10 or newer.

## Quick start

Pass document content, bytes, or a `Path` to `Lumberjack.saw()`:

```python
from pathlib import Path

from lumberjack import Lumberjack

jack = Lumberjack(max_tokens=1200)
result = jack.saw(Path("handbook.md"))

for chunk in result.chunks:
    print(chunk.own_heading, chunk.body, chunk.token_count)

print(result.document.metadata)
```

For in-memory content, pass a string directly. A plain string is always treated
as content, never as a filesystem path:

```python
result = Lumberjack(max_tokens=500).saw(
    "# Deployment\n\nDeploy the service with the approved release workflow."
)
```

`Lumberjack.saw()` returns a `SplitResult` containing the parsed `DocTree` and
the final `chunks`. Each chunk is a `Chunk` dataclass whose `body` contains the rendered content;
`ancestor_headings` and `own_heading` preserve the section context;
`token_count` is the final count after output processing. Document title, source
path, metadata, reference definitions, and line ranges are retained when available.

## Use it from the command line

```bash
# Format is inferred from the file extension.
lumber handbook.md --max-tokens 1200

# Select a tokenizer or a splitter when needed.
lumber report.docx --input-format docx --tokenizer tiktoken --splitter subtree

# JSON chunks are written to standard output.
lumber page.html --input-format html --splitter exact-sibling
```

The CLI emits JSON, so it can feed an indexing or ingestion job directly.

## Pick a splitting strategy

| Strategy | Best when you want |
| --- | --- |
| `sibling` (default) | Well-filled chunks that pack adjacent sibling sections while retaining their shared context. |
| `subtree` | A complete section subtree to stay together whenever it fits the budget. |
| `section` | Each section's direct body to be handled independently. |

The default strategies use incremental estimates for fast budget decisions.
Use `exact-sibling`, `exact-subtree`, or `exact-section` when every split-time
decision must recount the rendered candidate exactly. All chunks receive a
final authoritative count.

See [splitter strategies](docs/splitter-strategies.md) for practical strategy
examples.

## Web API

Install the `web` extra, then start the service:

```bash
lumberjack-serve --reload
```

It provides `POST /lumber/api/split/text` for pasted Markdown or HTML and
`POST /lumber/api/split/file` for uploaded Markdown, HTML, and DOCX files. Both
return the same serialized chunk shape as the Python API and CLI.

## Customize when you need to

The defaults are intended to be usable as-is. For advanced pipelines, you can
provide your own parser, tokenizer, splitter, normalizer, or transformer to
`Lumberjack(...)`. Built-in splitters accept typed `block_options` so tables,
code fences, and custom block kinds can have their own isolation and budget
policies. The public
extension points live under `lumberjack.parser`, `lumberjack.tokenizer`,
`lumberjack.splitter`, `lumberjack.block`, and `lumberjack.protocols`.

## Development

```bash
uv sync --group dev --group test --extra tokenizers --extra docx --extra web
UV_CACHE_DIR=/tmp/uvcache uv run pytest
```

## License

MIT
