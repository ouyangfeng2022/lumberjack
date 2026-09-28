<p align="center">
  <img src="assets/lumberjack-logo.svg" width="160" alt="Lumberjack logo: an axe, document, trees, and a tree ring" />
</p>

# Lumberjack

[![PyPI](https://img.shields.io/pypi/v/lumberjack-py.svg)](https://pypi.org/project/lumberjack-py/)
[![Python](https://img.shields.io/pypi/pyversions/lumberjack-py.svg)](https://pypi.org/project/lumberjack-py/)
[![Docs](https://img.shields.io/badge/docs-GitHub%20Pages-4051b5)](https://ouyangfeng2022.github.io/lumberjack/)
[![CI](https://github.com/ouyangfeng2022/lumberjack/actions/workflows/ci.yml/badge.svg)](https://github.com/ouyangfeng2022/lumberjack/actions/workflows/ci.yml)

Lumberjack is a document preprocessing library for retrieval-augmented generation (RAG). It converts documents into token-budgeted chunks, preserves document structure and source metadata, and splits tables by row with configurable header repetition.

Lumberjack can be used through the Python API, command-line interface, or Web API. Optional adapters support integration with LangChain, LlamaIndex, and Haystack.

[中文说明](README.zh-CN.md) · [Documentation](https://ouyangfeng2022.github.io/lumberjack/) · [PyPI](https://pypi.org/project/lumberjack-py/)

## Three ways to use Lumberjack

### 1. Python API

Pass text, bytes, a file path, or a `Document` to `Lumberjack.saw()`. The result contains the parsed document and finalized chunks.

```python
from lumberjack import Lumberjack

result = Lumberjack(max_tokens=500).saw("""
# Deployment

Deploy through the approved release workflow.
""")

for chunk in result.chunks:
    print(chunk.body, chunk.token_count)
```

For multiple documents, `saw_many()` returns results as an iterator. See the [Python API reference](https://ouyangfeng2022.github.io/lumberjack/reference/python/).

### 2. Command line

Pass a file, directory, or glob to `lumber`. The command-line interface emits JSON and supports batch output, with one result file per input document.

```bash
pip install lumberjack-py
lumber handbook.md --max-tokens 1200
lumber 'docs/**/*.md' --recursive --output-dir chunks/
```

Use `--input-format` to select a parser explicitly. For row- or record-oriented inputs such as CSV, TSV, JSONL, and logs, select `--splitter record`. See the [CLI reference](https://ouyangfeng2022.github.io/lumberjack/reference/cli/).

### 3. Web API

Install the `web` extra and start the service. Submit text or upload a file; the response contains the resulting chunks in JSON format.

```bash
pip install 'lumberjack-py[web]'
lumberjack-serve --host 127.0.0.1 --port 9612
```

The API provides `POST /lumber/api/split/text` and `POST /lumber/api/split/file`. Interactive request documentation is available at `http://127.0.0.1:9612/docs` while the service is running.

## What it does well

- **Broad format support.** Markdown, HTML, DOCX, PDF, plain text and logs, CSV/TSV, JSON/JSONL, XML, YAML/TOML, XLSX, SQLite/SQL, source code, and Jupyter notebooks are parsed into a shared document model. Model-based tokenizers and enhanced code parsing require optional dependencies.
- **Structure and provenance.** Heading context is retained with each chunk. Record-oriented inputs preserve row, field, sheet, and source-location metadata rather than being represented as artificial sections.
- **Row-aware table splitting.** Markdown and HTML tables are split at row boundaries. Table headers are repeated in each generated chunk by default and can be configured by table type.
- **Content-aware splitting.** Code fences retain their delimiters when split. Lists and other block types have dedicated handling. Protected blocks that cannot be split safely may exceed the configured token budget.
- **Configurable chunk organization.** Select sibling-section packing, subtree-first grouping, per-section processing, or record-aware packing for flat inputs.
- **Token-budget controls.** The default approximate tokenizer requires no model download. Optional `tiktoken` and Transformers tokenizers provide model-based counts. Exact and incremental counting modes can be selected independently.

## Supported input formats

| Family | Formats | Notes |
| --- | --- | --- |
| Documents | Markdown, HTML, DOCX, PDF | Headings, paragraphs, lists, tables, code, and document properties where available. PDF conversion stays local through MarkItDown; use MinerU or PaddleOCR for scanned PDFs. |
| Text and records | TXT, LOG, CSV, TSV, JSON, JSONL, XML, YAML, TOML | Record formats preserve logical row/field paths; use the `record` splitter for flat record packing. |
| Spreadsheets and databases | XLSX, SQLite, SQL dumps | SQLite uses the standard library. |
| Code and notebooks | Python, JavaScript/TypeScript, Bash, C/C++, C#, Go, Java, Kotlin, Lua, PHP, Ruby, Rust, Swift, Zig, Jupyter notebooks | The `code-parsing` extra adds Tree-sitter declaration boundaries and syntax-error recovery. |

RTF, ODT, legacy Excel, image, presentation, and columnar formats are not currently supported.

## Table splitting

Tables are treated as structured blocks. When a table exceeds its block budget, Lumberjack groups complete rows into separate chunks and repeats the Markdown header and delimiter, or the HTML table header, by default. Set `repeat_header=False` to omit the header from subsequent chunks. A row that individually exceeds the budget is preserved intact and may cause its chunk to exceed that budget.

Python callers configure tables with typed options:

```python
from lumberjack import Lumberjack
from lumberjack.block import MarkdownTableConfig
from lumberjack.splitter import SectionSplitter
from lumberjack.tokenizer import ApproxByteTokenizer

tokenizer = ApproxByteTokenizer()
splitter = SectionSplitter(
    tokenizer,
    max_tokens=500,
    block_options=[MarkdownTableConfig(repeat_header=True, max_tokens=300)],
)
result = Lumberjack(tokenizer=tokenizer, splitter=splitter).saw("report.md")
```

The CLI accepts equivalent settings, for example `--block table:repeat-header=false,max-tokens=300`. HTML tables use `HTMLTableConfig` in Python or `html_table` in CLI configuration.

## Choosing a splitter

| Splitter | Behavior |
| --- | --- |
| `section` (default) | Processes each section's direct body independently. |
| `subtree` | Keeps a section subtree together when it fits. |
| `sibling` | Packs adjacent sibling sections when they fit. |
| `record` | Packs flat rows or records, for CSV/TSV, JSONL, logs, and similar inputs. |

The `exact-*` variants recount candidate text during planning. The default and `incremental-*` variants use incremental counts during planning and report a final authoritative count. Tokenizer choice is independent of counting mode.

## Install optional features

```bash
# Model tokenizers, Web API, and Tree-sitter parsing
pip install 'lumberjack-py[tokenizers,web,code-parsing]'

# Optional framework adapters
pip install 'lumberjack-py[langchain,llama-index,haystack]'
```

Framework adapters are available under `lumberjack.integrations`. They convert chunks to framework documents or nodes and provide native splitter or parser components. See the [integration guides](https://ouyangfeng2022.github.io/lumberjack/guides/integrations/).

## Learn more

- [Core concepts](https://ouyangfeng2022.github.io/lumberjack/concepts/pipeline/) — document parsing, chunking, rendering, and source metadata.
- [Configuration guide](https://ouyangfeng2022.github.io/lumberjack/guides/configuration/) — block policies and budget controls.
- [Custom components](https://ouyangfeng2022.github.io/lumberjack/guides/custom-components/) — parsers, tokenizers, splitters, and post-processing.
- [Contributing](CONTRIBUTING.md) · [Security](SECURITY.md) · [License](LICENSE)
