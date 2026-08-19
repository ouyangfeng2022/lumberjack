<p align="center">
  <img src="assets/lumberjack-logo.svg" width="160" alt="Lumberjack logo: an axe, document, trees, and a tree ring" />
</p>

# Lumberjack

[![PyPI](https://img.shields.io/pypi/v/lumberjack-py.svg)](https://pypi.org/project/lumberjack-py/)
[![Python](https://img.shields.io/pypi/pyversions/lumberjack-py.svg)](https://pypi.org/project/lumberjack-py/)
[![Docs](https://img.shields.io/badge/docs-GitHub%20Pages-4051b5)](https://ouyangfeng2022.github.io/lumberjack/)
[![CI](https://github.com/ouyangfeng2022/lumberjack/actions/workflows/ci.yml/badge.svg)](https://github.com/ouyangfeng2022/lumberjack/actions/workflows/ci.yml)

**Turn Markdown, HTML, and DOCX into retrieval-ready chunks without losing their structure or heading context.**

Lumberjack is a Python library and CLI for RAG preprocessing. It reads a document tree instead of cutting plain text, preserves headings and source metadata, respects tables and fenced code, and keeps every chunk within a token budget whenever its content can be split safely.

[中文说明](README.zh-CN.md) · [Documentation](https://ouyangfeng2022.github.io/lumberjack/) · [PyPI](https://pypi.org/project/lumberjack-py/)

## Why Lumberjack?

- **Context survives splitting.** Chunks separate heading metadata from body content, so retrieval can retain the section that introduced an answer.
- **Document structure comes first.** Markdown, HTML, and DOCX become one format-neutral `DocTree` before splitting.
- **Budgets are practical.** The default splitter plans with fast incremental estimates, then records an authoritative final token count.
- **Topology is your choice.** Pack sibling sections, preserve subtrees, or process each section body independently.

## Input formats: now and planned

Lumberjack currently supports the formats below. A “planned” entry is a design
commitment, not an installation promise: do not pass it to `format` or rely on
automatic detection until it is marked supported in a release.

| Format family | Formats | Status | Intended structural model |
| --- | --- | --- | --- |
| Markup documents | Markdown (`.md`, `.markdown`), HTML (`.html`, `.htm`) | Supported | Headings, blocks, tables, lists, code, and source lines. |
| Word-processing documents | DOCX (`.docx`) | Supported | Heading styles, paragraphs, tables, lists, and document properties. |
| Plain and rich text | TXT, text logs, RTF | Planned | Ordered paragraphs/lines; no invented heading hierarchy. |
| OpenDocument and legacy word processing | ODT, DOC | Planned | Headings and blocks when the source format exposes them. |
| Spreadsheets and delimited data | XLSX, XLS, ODS, CSV, TSV | Planned | Schema/header plus atomic rows or configurable row groups; cells in a row must stay attributable to that row. |
| Semi-structured data | JSON, JSONL, XML, YAML, TOML | Planned | Objects, records, arrays, and paths—not artificial document headings. |
| Analytical and database exports | Parquet, Avro, ORC, SQLite/SQL dumps | Planned | Tables, record batches, schemas, and query/table provenance. |
| Source code and notebooks | Python, JavaScript/TypeScript, Java, C/C++, Go, Rust, Jupyter notebooks (`.ipynb`) | Planned | Files, symbols, comments, cells, and language-aware code blocks. |
| Presentations and ebooks | PPTX, PPT, ODP, EPUB | Planned | Slides/pages, titles, notes, and ordered content blocks. |
| Messages and archives | EML, MSG, MBOX | Planned | Message headers, body, attachments, and thread provenance. |
| PDFs and images | PDF, PNG, JPG/JPEG, TIFF, WebP | Planned | Native PDF text/layout where available; OCR/layout blocks and page provenance otherwise. |

Flat data is a first-class design case, not a disguised heading tree. CSV,
TSV, JSONL, Parquet, and record-oriented JSON will use ordered record/row units
with schema and field-path provenance. Heading-oriented policies such as
sibling section packing are not meaningful for those inputs; their adapters
must select row/record-aware packing, preserve complete protected rows when
configured, and report logical locations such as row number, column name, JSON
path, page, or sheet. This behavior is planned; it is not implemented by the
current three parsers.

## Inspect every pipeline stage

Today, `Lumberjack.saw()` returns `SplitResult(document, chunks)`, and the
public parser, splitter, and finalizer can be called individually when an
integration needs an intermediate `DocTree` or `ChunkDraft`.

The planned pipeline trace API will make every built-in and optional parsing
stage inspectable through one stable result: raw `Document`, extraction output
(for example OCR/layout), normalized `DocTree`, `ChunkDraft`s, rendered text,
normalized/transformed text, and final `Chunk`s. Visual PDF parsers such as
MinerU, Docling, PaddleOCR-VL, and dots.mocr will be optional integrations—not
core dependencies—and will retain page, bounding-box, and parser provenance.

## Install

```bash
pip install lumberjack-py

# Exact tokenizers, DOCX support, and the Web API
pip install "lumberjack-py[tokenizers,docx,web]"
```

Requires Python 3.10 or newer.

## Split your first document

```python
from lumberjack import Lumberjack

result = Lumberjack(max_tokens=500).saw("""
# Deployment

Deploy the service through the approved release workflow.

## Rollback

Keep the previous image available until health checks pass.
""")

for chunk in result.chunks:
    print(chunk.own_heading, chunk.body, chunk.token_count)
```

`result.document` contains the parsed `DocTree`, title, metadata, and source provenance. Each `Chunk` includes its body, final `token_count`, heading context, and source line range when available. See the [five-minute guide](https://ouyangfeng2022.github.io/lumberjack/getting-started/quickstart/) for file inputs, output handling, and optional dependencies.

## Use the CLI

```bash
# Infer supported Markdown, HTML, or DOCX from the file extension.
lumber handbook.md --max-tokens 1200

# Emit JSON suitable for an ingestion job.
lumber report.docx --tokenizer tiktoken --splitter subtree > chunks.json
```

The [CLI reference](https://ouyangfeng2022.github.io/lumberjack/reference/cli/) lists every option and its default.

## Choose a splitter

| Splitter | Choose it when you need |
| --- | --- |
| `sibling` | Well-filled chunks that may pack adjacent sibling sections with shared context. |
| `subtree` | A whole section subtree to stay together whenever it fits. |
| `section` (default) | Each section's direct body to be considered independently. |

| Counting mode | Behavior |
| --- | --- |
| Unprefixed / `incremental-*` | Fast running estimates while planning, followed by a final authoritative count. |
| `exact-*` | Fully recount each rendered candidate during planning. |

Tokenizer choice and counting mode are independent. For example, `tiktoken` works with `incremental-sibling`. Read the [splitter decision guide](https://ouyangfeng2022.github.io/lumberjack/concepts/splitting/) before tuning a production pipeline.

## Web API

```bash
lumberjack-serve --reload
```

With the `web` extra installed, the service exposes `POST /lumber/api/split/text` for Markdown/HTML JSON requests and `POST /lumber/api/split/file` for uploaded Markdown, HTML, and DOCX. The planned formats above are not accepted yet. FastAPI serves interactive OpenAPI documentation at [`/docs`](http://127.0.0.1:9612/docs) while the server is running.

## Learn more

- [Core concepts](https://ouyangfeng2022.github.io/lumberjack/concepts/pipeline/) — `Document` to `Chunk`, rendering, budgets, and source metadata.
- [Configuration guide](https://ouyangfeng2022.github.io/lumberjack/guides/configuration/) — block policies and budget controls.
- [Custom components](https://ouyangfeng2022.github.io/lumberjack/guides/custom-components/) — parsers, tokenizers, splitters, and post-processing stages.
- [Python API reference](https://ouyangfeng2022.github.io/lumberjack/reference/python/)
- [Contributing](CONTRIBUTING.md) · [Security](SECURITY.md) · [License](LICENSE)

Benchmark reporting is under construction; this project does not make unverified quality or performance claims.
