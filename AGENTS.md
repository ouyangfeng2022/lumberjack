# lumberjack Development Notes

## Project

The project is in the **development stage** and compatibility does not need to be considered. Allow all disruptive changes.

Structure-aware document splitter for RAG preprocessing: Markdown, HTML, DOCX, plain text/log, CSV/TSV, JSON/JSONL/XML/YAML/TOML, XLSX, SQLite/SQL dumps, and source code/notebooks. Python 3.10+, `src/` layout, built with `hatchling` + `hatch-vcs`.

Current runtime dependencies:

- `markdown-it-py[linkify,plugins]>=4.0.0` for the default GFM-like parser
- `pyyaml>=6.0` for YAML front matter and YAML records

Optional dependencies:

- `tiktoken>=0.9.0`, `cachetools>=7.1.1`, `transformers>=4.41.0` for model-based token counting (install via `--extra tokenizers`)
- `python-docx>=1.1.0` for DOCX document support (install via `--extra docx`)
- `fastapi>=0.115.0`, `uvicorn>=0.34.0`, `python-multipart>=0.0.18` for the web server (install via `--extra web`)
- `openpyxl>=3.1.0` for XLSX support (install via `--extra spreadsheets`)
- `tomli>=2.0.0` on Python < 3.11 for TOML records (install via `--extra toml`)
- tree-sitter language wheels for declaration-aware source parsing (install via `--extra code-parsing`; the built-in fallback works without it)
- `langchain-core`/`langchain-text-splitters`, `llama-index-core`, or `haystack-ai` for the RAG framework adapters (install via `--extra langchain` / `--extra llama-index` / `--extra haystack`)

## Commands

```bash
# Install dev, test, tokenizer, and DOCX dependencies
uv sync --group dev --group test --extra tokenizers --extra docx --extra web

# Run CLI (Markdown)
uv run lumber path/to/file.md --max-tokens 1200 --merge-below-ratio 0.125
# Run CLI with tiktoken on the incremental splitter
uv run lumber path/to/file.md --tokenizer tiktoken --splitter incremental-sibling --max-tokens 1200

# Run CLI (DOCX)
uv run lumber path/to/file.docx --input-format docx --max-tokens 1200

# Run CLI batch mode (directory in, one JSON per file; logs go to stderr)
uv run lumber docs/ --output-dir out/ --recursive --fail-fast

# Inspect parser output for one file (DocTree JSON; --outline prints the section tree)
uv run python -m lumberjack.parser path/to/file.md --outline

# Inspect splitter output for one file (same JSON envelope as `lumber`)
uv run python -m lumberjack.splitter path/to/file.md --splitter sibling --max-tokens 800

# Show CLI help
uv run lumber --help

# Run web server (development)
uv run lumberjack-serve --reload

# Run web server (production)
uv run lumberjack-serve --host 0.0.0.0 --port 8000

# Frontend (bun only; from lumberjack_webui/)
# bun install --frozen-lockfile && bun run lint && bun run build

# Run tests
uv run pytest
uv run pytest tests/parser/markdown/test_markdown_parser.py
uv run pytest tests/splitter/test_splitter.py
uv run pytest tests/parser/docx/test_docx_parser.py
uv run pytest tests/web/test_web.py

# Type check, lint, and format
uv run ty check .
uv run ruff check --fix
uv run ruff format

# Run Python scripts
uv run python xxx.py
```

## Architecture

Core pipeline:

```
Document -> Parser.parse() -> DocTree -> Splitter.split() -> ChunkDraft[]
     -> ChunkFinalizer.finalize() -> TextNormalizer -> TextTransformer -> Chunk[]
```

Every supported format produces the same `DocTree` (with `SectionNode` tree and `DocumentBlock` children), so all splitters work with any format. Public component namespaces own their implementations directly; the removed feller/sawyer/scaler/core paths have no compatibility aliases.

Main components:

### Shared public modules

- **Models**: `src/lumberjack/models.py`
  - `Document` — raw input plus format, title, metadata overrides, and provenance
  - `DocumentInline`, `DocumentBlock`, `SectionNode`, `DocTree` — shared across formats
  - `SourceLocation` — format-neutral provenance (byte/line range, page, sheet, row, column, JSON path, element ID, bounding box)
  - `ExtractionResult`, `PipelineDiagnostic`, `PipelineTrace` — stage-level results for external parsers and explicit trace runs
  - `ChunkDraft` — internal output of sawing; `Chunk` — final output of finalizeing
  - `SplitResult` — single-document result; `DocumentResult` — per-input batch result from `Lumberjack.saw_many()`
- **Protocols**: `src/lumberjack/protocols.py`
  - `TokenizerProtocol`, `ParserProtocol`, `SplitterProtocol`, `TextNormalizerProtocol`, `TextTransformerProtocol`
- **Tokenizer**: `src/lumberjack/tokenizer.py`
  - `ApproxByteTokenizer` (default, estimates tokens as UTF-8 bytes ÷ 3), `TiktokenTokenizer` and `TransformersTokenizer` (optional)
- **Block configuration**: `src/lumberjack/block.py`
  - `BlockKind`, `BlockConfig`, `MarkdownTableConfig`, `HTMLTableConfig`, and `CustomBlockConfig`
  - Python `block_options` accepts a sequence of these objects; CLI/Web adapters convert their external mapping formats at the boundary
- **Serialization**: `src/lumberjack/serialization.py`
  - `chunk_to_dict`/`chunk_from_dict`, `doc_tree_to_dict`/`doc_tree_from_dict`, `split_result_to_dict`/`split_result_from_dict` with stable `schema_version` markers; CLI and Web share these serializers; JSON Schemas live in `schemas/`
- **Splitters**: `src/lumberjack/splitter/` — public implementations operating on `DocTree`, format-agnostic
  - `base.py` provides `BaseSplitter` shared state and helpers; `context.py` provides the exact/incremental counting contexts
  - `sibling.py` provides `SiblingSplitter` — structure-first, budget-aware sibling packing
  - `subtree.py` provides `SubtreeSplitter` — subtree-first collapse with section fallback
  - `section.py` provides `SectionSplitter` — direct-body recursion with no subtree collapse
  - `record.py` provides `RecordSplitter` — row/record-aware packing for flat inputs (CSV/TSV, JSONL, logs); selected via the `record` splitter name
  - `topology/` holds shared section/subtree/sibling topology helpers
  - Unprefixed class names use incremental counting and `Exact*Splitter` names use full recounting
- **ChunkFinalizer stages**: `finalizer.py`, `normalizer.py`, and `transformer.py`
  - `ChunkFinalizer` renders drafts, applies `TextNormalizer` then `TextTransformer`, performs authoritative counts, and emits chunks
  - `PlainTextTransformer` is opt-in; default stages preserve Markdown surface syntax
- **Integrations**: `src/lumberjack/integrations/`
  - `chunk_metadata` plus eager `to_langchain_document(s)` / `to_llamaindex_node(s)` / `to_haystack_document(s)` converters and `build_*` index/store helpers
  - Lazily imported native pipeline components: `LumberjackTextSplitter`/`LumberjackDocumentTransformer` (LangChain), `LumberjackNodeParser`/`LumberjackReader` (LlamaIndex), `LumberjackDocumentSplitter` (Haystack)
- **Private helpers**: `src/lumberjack/_internal/`
  - `block_splitter.py` handles oversized blocks, `options.py` converts CLI/Web block configuration, `formats.py` detects integration input formats, `pipeline.py` orchestrates CLI/Web components, `rendering.py` contains shared rendering helpers, `trace.py` selects trace stages, and `xml_safe.py` rejects DTD/entity payloads before XML parsing

### Parsers (`src/lumberjack/parser/`)

Format-specific parsers — each turns one input format into the shared `DocTree`.

- **Auto selection**: `src/lumberjack/parser/auto.py`
  - `AutoParser` infers the format from explicit `format`, filename suffix, and content sniffing; `InputFormat` is the canonical literal union
  - `python -m lumberjack.parser FILE` prints the parsed `DocTree` as versioned JSON (`--outline` for the section tree)
- **Builder**: `src/lumberjack/parser/builder.py`
  - `DocTreeBuilder` is the supported construction layer for third-party parsers: `add_section`, `add_block`, `add_record`, `add_field_value`, `declare_block_kind`, `build` with structural validation and `SourceLocation` provenance

#### Markdown (`src/lumberjack/parser/markdown/`)

- **Parser**: `src/lumberjack/parser/markdown/parser.py`
  - `MarkdownParser` aliases `MarkdownItParser`
  - Uses `MarkdownIt("gfm-like")` with built-in plugins
  - `MarkdownItParser(disable_lheading=True)` to disable Setext heading parsing
  - Parses YAML front matter, preserves heading hierarchy, inlines, reference definitions, line ranges
- **Plugins**: `src/lumberjack/parser/markdown/plugins/`
  - `brackets_math_plugin`: `\[...\]` block math and `\(...\)` inline math syntax

#### DOCX (`src/lumberjack/parser/docx/`)

- **Parser**: `src/lumberjack/parser/docx/parser.py`
  - `DocxParser` — parses DOCX into `DocTree`
  - Maps Heading styles -> `SectionNode`, paragraphs -> `paragraph`, tables -> `table`, lists -> `list`, etc.
  - Iterates body elements in document order to preserve paragraph/table sequence
  - Extracts core properties as document metadata

#### HTML (`src/lumberjack/parser/html/`)

- **Parser**: `src/lumberjack/parser/html/parser.py`
  - `HTMLParser` — parses HTML into `DocTree`, mirroring Markdown and DOCX parsers
  - Built on stdlib `html.parser.HTMLParser` (aliased internally as `_StdlibHTMLParser` to avoid name shadowing)
  - `_HTMLDocumentBuilder` is the event-driven internal builder
  - Maps headings -> `SectionNode`, paragraphs -> `paragraph`, tables -> `html_table`, lists -> `list`, etc.
- **Table utility**: `src/lumberjack/parser/html/table_parser.py`
  - `HTMLTableParser` + `HTMLTable`/`HTMLTableRow`/`HTMLTableCell` dataclasses
  - Consumed by the Markdown parser and `_internal/block_splitter.py`; not used by `HTMLParser` itself

#### Records — text, tables, semi-structured (`src/lumberjack/parser/records/`)

- **Parser**: `src/lumberjack/parser/records/parser.py`
  - `TextParser` (TXT/LOG-style plain text via `TextParser`/`LogParser`), `DelimitedTextParser` (CSV/TSV), `JSONParser`, `JSONLinesParser`, `XMLParser`, `YAMLParser`, `TOMLParser`
  - Flat inputs become ordered `tabular_row`/record blocks under the root — no synthetic headings; keys are never turned into Markdown headings

#### Spreadsheet and database (`src/lumberjack/parser/xlsx/`, `src/lumberjack/parser/sqlite/`)

- `XlsxParser` preserves workbook/sheet/header/row provenance (needs the `spreadsheets` extra)
- `SQLiteParser` reads table schemas and rows from dump output only — document-supplied identifiers are never interpolated into queries (needs no extra)

#### Source code and notebooks (`src/lumberjack/parser/code/`)

- `SourceCodeParser` covers Python/JS/TS/Bash/C/C++/C#/Go/Java/Kotlin/Lua/PHP/Ruby/Rust/Swift/Zig; `NotebookParser` covers `.ipynb`; `SQLParser` covers SQL dumps
- `tree_sitter.py` adds declaration-aware boundaries via the `code-parsing` extra, with a built-in fallback when it is not installed

### Public API

- `src/lumberjack/__init__.py` — exports only `Lumberjack` and `Document`
- `src/lumberjack/lumberjack.py` — `Lumberjack.saw()` single-document API and `Lumberjack.saw_many()` streaming batch API returning `Iterator[DocumentResult]`
- `src/lumberjack/parser/` — `AutoParser`, `DocTreeBuilder`, concrete parsers, and Markdown plugin extensions
- `src/lumberjack/splitter/` — default incremental splitters, explicit `Exact*Splitter` classes, and `RecordSplitter`
- `src/lumberjack/tokenizer.py` — tokenizer implementations
- `src/lumberjack/finalizer.py`, `normalizer.py`, `transformer.py` — final processing stages
- `src/lumberjack/serialization.py` — stable schema-versioned serializers shared by CLI/Web
- `src/lumberjack/integrations/` — optional RAG framework adapters (lazy imports; core install stays framework-free)
- `src/lumberjack/block.py` — typed block configuration
- `src/lumberjack/models.py` and `src/lumberjack/protocols.py` — shared data and extension contracts
- `src/lumberjack/_internal/` — private cross-component helpers used by built-ins and integrations
- `src/lumberjack/core/` does not exist and is not a compatibility import path

### Web API / UI

- **Web API**: `src/lumberjack/web/` — FastAPI with `/split/text` and `/split/file` endpoints
- **Web UI**: `lumberjack_webui/` — React 19 + TypeScript + Vite

## Data Model

Defined in `src/lumberjack/models.py`.

## Web API

Implemented in `src/lumberjack/web/` (app factory in `app.py`, routes in `routes.py`).

- `POST /lumber/api/split/text` — JSON body with `text` and split options
- `POST /lumber/api/split/file` — multipart form with `file` upload and split options
  - Supports `input_format` form field: `auto` (detect from extension) or any supported format; binary formats (`docx`, `xlsx`, `sqlite`) are passed through as bytes
- Both endpoints accept `trace_stages` (repeatable) and `trace_max_bytes` for size-capped selective stage output
- Response: JSON with `schema_version`, `document`, `metadata`, `chunk_count`, `chunks` array, and optional `trace`
- Static Web UI assets are mounted only when built; otherwise the server runs API-only
- Server CLI: `lumberjack-serve` with `--host`, `--port`, `--reload`

## CLI Behavior

Implemented in `src/lumberjack/cli.py`.

- Input is a file path, a directory, or a glob of supported documents
- `--input-format`: `auto` (detect from extension) or any of `markdown`, `html`, `docx`, `text`, `log`, `csv`, `tsv`, `json`, `jsonl`, `xml`, `yaml`, `xlsx`, `toml`, `sqlite`, `sql`, source-code names (`python` … `zig`), `notebook`
- Output format: JSON only; `--jsonl` emits one result record per line for batch runs
- Batch: `--output-dir` writes one JSON per input, `--recursive` recurses directories, `--overwrite` allows replacing outputs, `--fail-fast` stops at the first failure; progress/logs go to stderr so stdout stays pipeable
- Tokenizers (engine): `approx`, `tiktoken`, `transformers`
- Exact vs incremental counting is a property of the splitter class, not the tokenizer. CLI/Web retain their existing `splitter` and `tokenizer` field names as an integration protocol.
- Splitter choices: `sibling` (incremental), `subtree` (incremental), `section` (default, incremental), `exact-sibling`, `incremental-sibling`, `exact-subtree`, `incremental-subtree`, `exact-section`, `incremental-section`, and `record` for flat CSV/TSV/JSONL/log inputs
- `--block KIND:SETTING,...` per-block-kind config; repeatable across kinds
- Diagnostics: repeatable `--trace-stage` with `--trace-max-bytes` includes selected pipeline stages in the JSON output
- JSON output uses the shared schema-versioned serializers from `lumberjack.serialization`

## Splitting Rules

- Whole document is kept as one chunk when it already fits the budget
- `SiblingSplitter`: merges adjacent sibling sections when they fit within `max_tokens`
- `SectionSplitter` (default): handles each section's direct body independently without collapsing subtrees
- `SubtreeSplitter`: subtree-first collapse. `SectionSplitter`: always per-heading with no subtree-collapse.
- `RecordSplitter` (`record`): row/record-aware packing for flat inputs; hierarchical splitters never treat CSV/JSONL rows as sections, and un-splittable protected rows that exceed the budget are reported as protected blocks instead of fake compliance
- Tail-fragment merging (`merge_below_ratio`, default `0.125`): bottom-up, merges same-heading adjacent `paragraph` chunks whose tail is below `int(max_tokens * ratio)` tokens, when the merged result fits `max_tokens`. Disabled when `ratio == 0`. In the `section` splitter this runs only within each section's direct-body drafts, so it cannot collapse subtrees or merge non-text block chunks.
- Text fallback order is paragraph break -> line break -> sentence -> word -> hard split
- `Chunk.body` always includes rendered heading context; shared parent headings are deduplicated
- `skip_empty_sections=True` discards chunks that contain only a heading with no body content
- `block_options` is a sequence of typed objects from `lumberjack.block`; duplicate kinds are rejected
- Exact `Exact*Splitter` classes fully recount rendered text at every budget decision without the tokenizer text cache (`use_tokenizer_cache = False`): every document's split starts from a zero cache in production and caches are never reused across documents. Identical texts within one split (repeated heading paths, bodies counted at both the call site and the draft builder) are deduplicated by a per-split memo (`_memo_count`), mirroring incremental's `_count_once`. Default unprefixed splitters use a running additive estimate with a per-split `_count_once` memo. `ChunkFinalizer` performs the authoritative final recount after seasoning and planing.

## Constraints

- Supported input formats: Markdown, HTML, DOCX, TXT/LOG, CSV/TSV, JSON/JSONL/XML/YAML/TOML, XLSX, SQLite/SQL, source code, and notebooks (RTF/ODT/DOC/XLS/ODS/Parquet/Avro/ORC and PDF are deliberately deferred)
- Oversized fenced code blocks are split into re-fenced segments by default (`BlockConfig.split=True`); configure `code_block`/`code_fence` with `split=False` to preserve them intact even when they exceed `max_tokens`
- CLI should stay orchestration-only; parsing and splitting logic belongs to the public component implementations, while integration adapters belong in `src/lumberjack/_internal/`
- The core package has no LangChain/LlamaIndex/Haystack/Docling/Unstructured dependency; framework adapters live in `src/lumberjack/integrations/` behind optional extras and lazy imports

## Testing

Tests use `pytest`. `tests/conftest.py` adds `src/` to `sys.path`.

Parser verification has three layers, all under `benchmarks/`:

- `benchmarks/parser_run.py` — pinned external corpora (Markdown, DOCX, HTML incl. html5lib fragments and MDN pages); sources are declared in `benchmarks/datasets/parser_sources.json` and fetched with `benchmarks/fetch_parser_corpora.py`
- `benchmarks/random_run.py` + `benchmarks/random_corpus.py` — seeded random-document generators for every parser beyond Markdown/DOCX, checked against generated visible-text recall, exact element counts, and clean rejection of adversarial payloads
- `tests/parser/test_parser_robustness.py` — combinatorial syntax corpora, adversarial fragments, and invalid-input rejection tests for Markdown, DOCX, HTML, records, spreadsheet, database, and source parsers

Splitter verification has its own random benchmark: `benchmarks/splitter_random_run.py` + `benchmarks/splitter_random_corpus.py` measure the six hierarchical splitter variants (section/subtree/sibling topology × exact/incremental counting) over seeded synthetic structural shapes plus recombined real corpora, comparing clean wall time (repetitions without tracemalloc, with the tokenizer text cache cleared before every repetition — warmup only loads the tokenizer and reaches steady state), cold-run tracemalloc allocation peaks, tokenizer call counts, and the split-time estimate vs authoritative token-count error under identical tokenizers. `benchmarks/splitter_report.py` renders the full comparison (length × splitter × counting mode × `max_tokens` budget; time/accuracy/memory) into a self-contained HTML report from the per-budget `raw.json` outputs.

Current test areas:

- Markdown parser heading-tree construction, inlines, line ranges
- DOCX parser heading parsing, table extraction, list detection, section tree structure
- Flat/record, spreadsheet, database, and source parsers (including robustness suites in `tests/parser/test_parser_robustness.py`)
- Section-aware chunking, budget management, merging, record splitting, token-counting modes
- Public `Lumberjack.saw()`/`saw_many()` APIs with multiple input formats
- Serialization round-trips against the JSON Schemas in `schemas/` (`tests/test_serialization.py`)
- Batch CLI behavior, trace-stage output, and `python -m` inspection entries
- Web API split with text input, file upload, error handling, and full options
- RAG framework adapters and native pipeline components (`tests/integrations/`, separate `integrations` dependency group)
- Distribution artifacts (`tests/test_distribution.py`) and Docker image (`tests/test_docker.py`)
- Benchmark harness contract, metrics, and corpus fetchers (`tests/benchmarks/`)

After Python code changes:

1. Run `uv run ty check .`
2. Run `uv run ruff check --fix`
3. Review whether `--unsafe-fixes` is actually needed before using it
4. Run `uv run ruff format`
5. Run the relevant `pytest` scope

## Changelog

`CHANGELOG.md` records changes that are user-visible — i.e. things a consumer of lumberjack would notice (new features, behavior changes, bug fixes, removed/renamed APIs, dependency changes, CLI/web option changes, etc.).

Whether to update `CHANGELOG.md` is judged on a **per-change basis**:

- **Update it** for changes a user could observe: new features, behavior changes, bug fixes, removed/deprecated API, changed CLI options, changed dependencies, performance changes.
- **Skip it** for purely internal changes that don't affect users: docs/typo fixes, comment tweaks, refactors with no behavior change, test-only changes, CI/internal tooling churn, formatting/lint fixes.

In short: if a user reading the changelog would not care about the change, it does not need an entry.

### Format

- Add entries under an `Unreleased` section at the top of the file.
- Follow the [Keep a Changelog](https://keepachangelog.com/) format and group entries by type:
  - `Added` for new features
  - `Changed` for changes in existing functionality
  - `Deprecated` for soon-to-be removed features
  - `Removed` for now removed features
  - `Fixed` for any bug fixes
  - `Security` for vulnerabilities
- Each entry should be a concise, user-facing description of the change, not an implementation detail.
- Create `CHANGELOG.md` if it does not yet exist.

## Versioning

Package versions are managed by Git tags through `hatch-vcs` (`dynamic = ["version"]` with `[tool.hatch.version] source = "vcs"` in `pyproject.toml`). Do not maintain a separate hard-coded package version unless the versioning strategy is deliberately changed.

### PyPI release runbook

The PyPI distribution is **`lumberjack-py`**. Keep the Python import package
(`lumberjack`) and CLI commands (`lumber`, `lumberjack-serve`) unchanged. Update
the distribution name consistently in `pyproject.toml`, README install commands,
badges, TestPyPI/PyPI URLs, extras' self-reference, artifact tests, and
`CHANGELOG.md`.

One-time remote configuration:

- Create PyPI and TestPyPI **pending trusted publishers** for `lumberjack-py`.
  Both use owner `ouyangfeng2022`, repository `lumberjack`; PyPI uses
  `release.yml` / `pypi`, and TestPyPI uses `test-release.yml` / `testpypi`.
- The GitHub `pypi` environment must permit only `v*` tags. The `testpypi`
  environment must permit `main` and `v*` tags, because its workflow is
  manually dispatched.
- Never store a long-lived PyPI token. The workflows use OIDC
  (`id-token: write`) and upload/download the built distributions as artifacts.

Release procedure:

1. Complete the normal verification: `uv run ty check .`, `uv run ruff check .`,
   `uv run ruff format --check .`, `uv run pytest -q`, frontend lint/build, then
   `uv build`, `twine check`, and distribution-content tests.
2. Move user-visible `CHANGELOG.md` entries from `Unreleased` into the intended
   stable version section. Commit and push the release preparation.
3. Test first on TestPyPI with an annotated RC tag such as `v0.4.0rc1`; manually
   dispatch `test-release.yml` using that tag. Install the exact candidate from
   TestPyPI in a new virtual environment and verify the import, `lumber --help`,
   and a basic `Lumberjack().saw()` call.
4. Do **not** put the RC and stable tag on the same commit. With `hatch-vcs`, a
   stable tag sharing a commit with `vX.Y.ZrcN` can build the RC version instead.
   Create a distinct release commit (an intentional empty release commit is
   acceptable) before annotating and pushing the stable `vX.Y.Z` tag.
5. `release.yml` accepts only stable `vX.Y.Z` tags, verifies that wheel metadata
   equals the tag version, runs full CI and package smoke tests, publishes to
   PyPI, and creates the GitHub Release. Do not create a stable tag until the
   TestPyPI candidate has been accepted.
6. After publish, install `lumberjack-py==X.Y.Z` from production PyPI in a new
   virtual environment and repeat the import/CLI/basic-split smoke test. Verify
   the PyPI project page and GitHub Release assets.

Troubleshooting learned from the first release:

- A TestPyPI upload from an untagged branch produces a Hatch VCS local version
  such as `0.3.1.dev13+g<sha>`; PyPI/TestPyPI rejects local version identifiers.
  Use an RC tag instead.
- A deployment rejection from `testpypi` can mean the environment allows only
  tags while `test-release.yml` was dispatched from `main`; add the `main`
  branch policy only to `testpypi`, never to production `pypi`.
- The publish job intentionally has no checkout. GitHub Release creation must
  not use `gh release create --verify-tag`, which requires a local `.git`
  directory. `gh release create "$GITHUB_REF_NAME" dist/* --generate-notes`
  works with the remote tag and downloaded artifacts.
- GitHub preserves failed deployment records from earlier attempts. Historical
  failures do not negate a later successful PyPI upload or GitHub Release;
  inspect each deployment's linked workflow step before acting.

Before every code push, decide whether the change set requires a version update:

- If the push is ordinary development work, no tag is required; `hatch-vcs` will expose a `.devN` version after the latest tag.
- If the push is a release or should produce a stable installable version, choose the next SemVer version, update the changelog release section, and create the corresponding Git tag (for example `v0.2.0`) before publishing.
- If the push contains user-visible behavior that is not being released yet, update `CHANGELOG.md` under `Unreleased` but leave the package version to the VCS-derived development version.
- If the push is docs-only, tests-only, formatting-only, or internal tooling-only, record that no version bump is needed.

### Commit workflow

When a change warrants a changelog entry, do it in the same commit (or PR) as the code change — never as a follow-up:

1. Make the code change.
2. Run the verification steps above (`ty check`, `ruff`, `pytest`).
3. If the change is user-visible, update `CHANGELOG.md` with an entry describing it.
4. Before pushing, decide whether the change set needs a release version tag, an `Unreleased` changelog entry only, or no version update.
5. Stage the code change **and** the `CHANGELOG.md` update together.
6. Commit (and, if applicable, push/PR) both in the same change set.

### Branch workflow

`main` is the production deployment branch. Create feature branches from `dev`
and merge ordinary development work back into `dev`; promote tested `dev`
changes to `main` through a separate release/deployment PR. Do not directly
push ordinary work to `main`.

## Code Organization

```
src/lumberjack/
    __init__.py                     # Public API: Lumberjack, Document
    lumberjack.py                   # saw()/saw_many() pipeline orchestrator
    cli.py                          # CLI orchestration
    block.py                        # Public block kinds and typed configuration
    models.py                       # Public shared data models (incl. trace models)
    protocols.py                    # Public extension protocols
    tokenizer.py                    # Public tokenizer implementations
    finalizer.py                    # ChunkDraft-to-Chunk finishing stage
    normalizer.py                   # Text stabilization stage
    transformer.py                  # Text normalization/plain-text stages
    serialization.py                # Schema-versioned serializers (CLI/Web shared)
    integrations/                   # Optional RAG framework adapters (lazy)
        _components.py, _metadata.py
        langchain.py, llama_index.py, haystack.py
        langchain_splitter.py, llama_index_pipeline.py, haystack_splitter.py
    web/                            # FastAPI layer
        app.py, routes.py, __main__.py
    parser/                         # Public parser implementations
        __init__.py                 # AutoParser, DocTreeBuilder, concrete exports
        __main__.py                 # `python -m lumberjack.parser` inspection entry
        auto.py                     # Format inference and parser selection
        builder.py                  # DocTreeBuilder for third-party parsers
        markdown/
            parser.py               # MarkdownItParser
            plugins/                # markdown-it plugins
        docx/
            parser.py               # DocxParser
        html/
            parser.py               # HTMLParser + _HTMLDocumentBuilder
            table_parser.py         # HTMLTableParser + HTMLTable*
        records/parser.py           # Text/Log/CSV/TSV/JSON/JSONL/XML/YAML/TOML
        xlsx/parser.py              # XlsxParser
        sqlite/parser.py            # SQLiteParser
        code/
            parser.py               # SourceCodeParser/NotebookParser/SQLParser
            tree_sitter.py          # Optional declaration-aware enhancement
    splitter/                       # Public splitter implementations
        __main__.py                 # `python -m lumberjack.splitter` inspection entry
        base.py, context.py
        exact.py, incremental.py
        sibling.py, subtree.py, section.py, record.py
        topology/
    _internal/                      # Private cross-component helpers
        block_splitter.py
        formats.py
        options.py
        pipeline.py
        rendering.py
        trace.py
        xml_safe.py
schemas/                            # chunk-v1 / doc-tree-v1 JSON Schemas
examples/                           # Runnable RAG framework demos
benchmarks/                         # Parser/splitter verification + benchmark MVP
lumberjack_webui/                   # React + TypeScript frontend
tests/                              # mirrors src/lumberjack layout
    __init__.py
    conftest.py
    helpers.py                      # shared test helpers (FIXTURES_DIR, etc.)
    test_api.py                     # tests package API and built-in components
    test_cli.py                     # tests src/lumberjack/cli.py
    test_docker.py                  # tests docker/Dockerfile
    test_lumber_pipeline.py         # tests saw()/saw_many() orchestration
    test_serialization.py           # tests schema round-trips
    _internal/                      # pipeline, rendering, xml_safe helpers
    benchmarks/                     # harness contract, metrics, fetchers
    contracts/                      # public-API contract tests
        test_cli_contract.py
        test_public_api_contract.py
        test_web_contract.py
    corpora/                        # parser validation corpora
    integrations/                   # framework adapters + demos
    parser/                         # covers src/lumberjack/parser/
        markdown/test_markdown_parser.py
        docx/test_docx_parser.py
        html/test_html_parser.py
        html/test_table_integration.py
        test_flat_parser.py         # records/text formats
        test_spreadsheet_parser.py  # XLSX
        test_database_parser.py     # SQLite/SQL
        test_source_parser.py       # code/notebooks
        test_parser_robustness.py   # adversarial inputs across parsers
        test_main_entry.py
    splitter/                       # covers src/lumberjack/splitter/
        test_splitter.py
        test_render_headings.py
        test_max_heading_level.py
        test_token_counting_modes.py
        test_main_entry.py
    web/test_web.py                 # tests src/lumberjack/web/
    fixtures/
        markdown/
        docx/
```
