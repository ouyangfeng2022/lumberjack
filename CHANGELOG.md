# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- Added component-oriented public modules and packages: `lumberjack.parser`, `lumberjack.splitter`, `lumberjack.tokenizer`, `lumberjack.block`, `lumberjack.models`, and `lumberjack.protocols`.
- Added `AutoParser` with suffix, DOCX structure, and HTML content detection; all parser objects now share `metadata_overrides` and `source_path` document arguments.
- Added typed block configuration with `BlockKind`, `BlockConfig`, table-specific configs, and `CustomBlockConfig`.

### Changed

- **Breaking:** `lumber()` is now a minimal convenience API accepting only `source`, `format`, and `max_tokens`; advanced use is composed explicitly from parser, tokenizer, and splitter objects.
- **Breaking:** Unprefixed `SiblingSplitter`, `SubtreeSplitter`, and `SectionSplitter` classes and CLI/Web names now use incremental measurement. Full recounting is selected through explicit `Exact*Splitter` classes or `exact-*` integration names.
- **Breaking:** Splitters accept validated constructor arguments directly. `SectionSplitter` no longer exposes the inapplicable `merge_below_ratio` argument.
- **Breaking:** `MarkdownParser` now disables Setext headings by default; pass `disable_lheading=False` to enable them.
- `DocumentAST.source_path` now records source provenance independently, and `Chunk.document_path` is generated from that field rather than semantic metadata.
- Public parser, splitter, tokenizer, block, model, and protocol namespaces now own their implementations directly instead of forwarding to a parallel `core` tree.
- **Breaking:** The public AST node types are now format-neutral: `MarkdownInline` and `MarkdownBlock` were renamed to `DocumentInline` and `DocumentBlock`. Their text is defined as canonical Markdown-like rendered content rather than a guaranteed source slice.
- The Web UI now sends `merge_below_ratio`, exposes every supported exact/incremental splitter name, and mirrors the complete serialized `Chunk` schema.

### Removed

- **Breaking:** Removed `SplitOptions`, dict-based Python `block_options`, `document_metadata`, public registry/factory helpers, and the `lumberjack.core` package. Public parsing is performed by parser objects; there is no module-level `parse()` function.
- **Breaking:** Removed the legacy `recursive`, `exact-recursive`, and `incremental-recursive` registry names and the `RecursiveSplitter` class aliases. Use the corresponding `sibling` names and classes.

### Fixed

- Tokenizer and splitter descriptions now consistently state that tokenizers encode/count text while splitters select exact or incremental measurement.

## [0.2.0] - 2026-07-16

### Added

- HTML document parsing via `HTMLParser`; `lumber()` and the CLI/web API now accept HTML text and `.html` files (`format="html"`).
- DOCX document parsing via `DocxParser`; `lumber()` now accepts DOCX bytes and `.docx` files (`format="docx"`), preserving paragraph/table/list order and extracting core properties as metadata.
- Token counting strategies: exact (full recount) and incremental (additive estimate) splitter variants, selectable through the `exact-*` / `incremental-*` registry names. Any tokenizer works with any splitter.
- Tokenizer engines `approx` (chars ÷ 4), `tiktoken`, and `transformers`, exposed via the `--tokenizer` CLI option and the `tokenizer` web/API parameter.
- `render_headings` split option to omit a chunk's ancestor heading breadcrumb from `Chunk.body` while keeping its own heading; both splitters are budget-aware around it.
- `max_heading_level` split option to cap how deep headings are retained as section context; deeper headings render as body text.
- `merge_below_ratio`, a tail-fragment merge threshold expressed as a fraction of `max_tokens` (default `0.125`).
- Per-heading `SectionSplitter` (registry `section`/`exact-section`/`incremental-section`) and subtree-first `SubtreeSplitter` (registry `subtree`/`exact-subtree`/`incremental-subtree`).
- Custom Markdown parser block handlers and plugin block specs for user-defined block kinds.
- HTML table parsing and oversized-table splitting (with optional header-row repetition on each piece).
- Web server runs in API-only mode when the frontend static assets are absent, instead of failing to start.
- CI workflow, contribution guides, and issue/PR templates.
- Docker deployment support.

### Changed

- **Breaking:** `lumber()` signature reworked. `text` now accepts `str | bytes | Path`; a `format` parameter (`"auto"`/`"markdown"`/`"html"`/`"docx"`) selects the parser. The `parser`, custom `tokenizer`, and custom `splitter` instance parameters were removed — only built-in name strings are accepted. Pass a custom parser/tokenizer/splitter by parsing manually and calling `splitter.split()`.
- **Breaking:** Removed the `merge_below_tokens`, `overlap_tokens`, `merge_small_chunks`, `recursive_split`, and `disable_lheading` parameters. Tail merging is now controlled by `merge_below_ratio`; oversized blocks are controlled by per-kind block options.
- **Breaking:** `BlockConfig` was renamed to `BaseParams` (with `TableBlockParams` for tables). The `--block-config` CLI strings use `KIND[:isolated][:nosplit][:TOKENS]`.
- **Breaking:** The section-family splitters were renamed so class and registry names describe their behavior. The subtree-first splitter (formerly `SectionSplitter`, registry `section`) is now `SubtreeSplitter` (registry `subtree`). The per-heading splitter (formerly `SectionFlatSplitter`, registry `section-flat`) is now `SectionSplitter` (registry `section`).
- `max_heading_level` is now applied by splitters, so parsers preserve the full heading tree while deeper headings render as chunk body text.
- Minimum Python version lowered from 3.13 to 3.10.
- Constrained the web dependency set to Starlette versions before 1.0 so FastAPI test clients continue to process requests.

### Removed

- `SectionFlatSplitter`, `ExactSectionFlatSplitter`, and `IncrementalSectionFlatSplitter` aliases and the `section-flat`/`exact-section-flat`/`incremental-section-flat` registry names. Use the renamed `SectionSplitter` (registry `section`) instead. The previous subtree-first `SectionSplitter`/`ExactSectionSplitter`/`IncrementalSectionSplitter` names are now `SubtreeSplitter`/`ExactSubtreeSplitter`/`IncrementalSubtreeSplitter`.
- The transient `subtree_merge` option, superseded by choosing between the `subtree` and `section` splitters.

### Fixed

- The CLI now validates `--block-config` entries against the input parser's known block kinds.
- The Markdown parser validates extra block kinds and block-spec token types.

## [0.1.0] - 2026-06-09

### Added

- Structure-aware Markdown splitting with recursive and section strategies.
- GFM-like parser with LaTeX math (dollarmath), YAML front matter, and bracket math plugins.
- CLI entry point: `lumber`.
- Web server entry point: `lumberjack-serve`.
- Python API: `lumberjack.lumber()`.
- Simple character and tiktoken tokenizer implementations.
- FastAPI web server with React frontend.
- PEP 561 type marker (`py.typed`).
