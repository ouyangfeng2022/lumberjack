# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Security

- Public web deployments now enforce resource limits: requests and uploads
  above a size ceiling return `413`, split execution runs under a concurrency
  limit and a wall-clock timeout (`503` on expiry), and split API calls are
  rate limited per client (`429`). All limits are configurable through
  `LUMBERJACK_WEB_*` environment variables and invalid values fail at startup.
  Error details are sanitized so parser failures cannot leak server file
  paths, and every response carries `X-Content-Type-Options` and
  `Referrer-Policy` headers. The web API documentation now states the privacy
  guarantees: uploads are processed in memory only and logs never contain
  document content.
- Untrusted XML parsing (DOCX parts, XML records, parser benchmarks) now
  rejects payloads containing DTD or entity declarations before parsing, and
  forbids DTDs on the underlying expat parser, closing the internal-entity
  expansion (billion laughs) resource-exhaustion vector.
- SQLite parsing now reads table schemas and row values from the connection's
  dump output, so the parser executes fixed SQL statements only and
  document-supplied table identifiers are never interpolated into a query.
- The benchmark corpus fetcher now validates download URLs before fetching:
  only `http`/`https` schemes are allowed and hosts resolving to loopback,
  private, link-local, multicast, reserved, or unspecified addresses are
  refused, including redirect targets.

### Fixed

- Seeded XLSX parser-benchmark documents now normalize ZIP member timestamps,
  so repeated generation produces identical bytes. CI also runs tokenizer and
  LlamaIndex integration tests offline; the LlamaIndex index helper skips its
  default splitter for already-final chunks, and the runnable LlamaIndex demo
  supplies local token counting to avoid implicit tiktoken downloads.

### Added

- Added `GET /health` and `GET /version` endpoints (also under
  `/lumber/api`) reporting the running package version and, when the
  `LUMBERJACK_BUILD_COMMIT` environment variable is set at deploy time, the
  deployed commit. Health probes are exempt from rate limiting.
- The Web UI gained a splitter comparison mode: built-in sample documents
  (technical, wide tables, long paragraphs, mixed Chinese/English, and
  code-heavy), topology and exact-vs-incremental presets plus custom splitter
  selections rendered side by side, a source-line boundary map that colors
  every line by its chunk, chunk cards showing `token_count`,
  `estimated_token_count` with the relative error, block kind, protected
  marking, heading breadcrumbs, and non-line source locations, copyable
  Python/CLI configuration for the current options, and JSON/JSONL result
  downloads.
- The benchmark dataset grew from 6 to 36 CC0 documents: five documents per
  scenario (technical, tables, code/formula, short sections, long paragraphs,
  mixed language) plus three Markdown/HTML cross-format equivalence groups
  sharing a `group` id. Benchmark adapters now receive the document format,
  so HTML corpus entries are parsed as HTML. The dataset version is
  `2026.08.27`.

### Added

- Added a `langchain-html` benchmark adapter (`HTMLHeaderTextSplitter`) so
  HTML corpus entries can be compared against LangChain's own HTML splitting;
  the `benchmark` dependency group now includes `beautifulsoup4`.
- Added `docling-hybrid` and `chonkie-table` benchmark adapters, completing
  the nine-variant competitor set. The hybrid adapter feeds Docling's
  `HybridChunker` with an offline UTF-8-bytes tokenizer so benchmark runs
  never download a HuggingFace model; the table adapter maps the token budget
  onto Chonkie's `TableChunker` (`chonkie>=1.7`). Both Docling adapters now
  support the `convert_string(content, format)` signature required by
  docling >= 2.120 while keeping compatibility with the older keyword form.
- Added three runnable end-to-end examples with CI smoke tests:
  `examples/technical_document.py` (structure-aware vs naive splitting with
  heading provenance), `examples/table_chunking.py` (header repetition and
  unsplittable tables under a tight budget), and
  `examples/incremental_counting.py` (exact vs incremental counting with
  tokenizer call counts, wall time, and estimate error). The splitter
  decision guide (`docs/splitter-strategies.md`, bilingual) was expanded to a
  full when-to-use/trade-off reference for every topology, counting mode, and
  budget knob.
- Added optional LangChain, LlamaIndex, and Haystack adapters for final
  `Chunk` objects.  All preserve JSON-safe chunk metadata and provenance while
  keeping `Chunk.body` as framework content; the LlamaIndex adapter also builds
  a ready-to-retrieve `VectorStoreIndex`. Runnable LangChain, LlamaIndex, and
  Haystack demos cover splitting, indexing, retrieval, and query/prompt
  construction. Install the corresponding
  `langchain`, `llama-index`, or `haystack` extra to use one.
- Added native RAG pipeline components that plug Lumberjack into each
  framework's own ingestion flow, replacing the built-in splitter:
  `lumberjack.integrations.LumberjackNodeParser` (LlamaIndex `NodeParser`
  with `SOURCE`/`PREVIOUS`/`NEXT` relationships, deterministic node ids, and
  suffix-based fallback routing) and `LumberjackReader` (a `BaseReader`
  rendering Markdown/HTML/DOCX into canonical Markdown), plus
  `LumberjackTextSplitter` / `LumberjackDocumentTransformer` (LangChain
  `TextSplitter` / indexing transformer) and `LumberjackDocumentSplitter`
  (a Haystack `@component`). The `langchain` extra now also installs
  `langchain-text-splitters`; all components are imported lazily so the core
  install stays framework-free.
- Added `emit_parents` to the LlamaIndex `LumberjackNodeParser`: it now emits
  one parent `TextNode` per real heading section, grouped from the leaf chunks
  under that section, with `PARENT`/`CHILD` relationships and deterministic
  parent ids, so `AutoMergingRetriever` merges retrieval hits into the actual
  section text instead of token-window pseudo-hierarchies.
- Added runnable module entries for stage-level inspection:
  `python -m lumberjack.parser FILE` prints the parsed `DocTree` as versioned
  JSON (or a section outline with `--outline`), and
  `python -m lumberjack.splitter FILE` prints the same chunk-result JSON
  envelope as the `lumber` CLI with the core split options
  (`--splitter`, `--tokenizer`, `--max-tokens`, ratio and heading controls).
  Both accept `-` to read text from stdin.
- Added large-scale randomized parser verification: seeded generators build
  documents for HTML, TXT/LOG, CSV/TSV, JSON/JSONL/YAML/TOML/XML, XLSX, SQLite,
  Python/JavaScript/TypeScript, notebooks, and SQL, and check each parser
  against generated visible-text recall, exact element counts, and clean
  rejection of damaged payloads (`benchmarks/random_run.py`).
- Added two version-pinned HTML corpora to the parser benchmark: html5lib
  tree-construction adversarial fragments and MDN Learning Area real-world
  pages, with an independent HTML visible-text reference extractor.
- Added combinatorial and adversarial robustness tests for the HTML, records,
  spreadsheet, database, and source parsers, including deterministic generated
  corpora and invalid-input rejection checks.

### Changed

- `Exact*Splitter` classes no longer enable the tokenizer text cache during
  splitting. Every document's split starts from a zero cache in production
  (text caches are request-local and never reused across documents) and a
  single split offers essentially no cache reuse, so exact recounting now pays
  the full encoding cost directly instead of populating an LRU; peak memory
  during exact splits no longer grows with the cache. The splitter benchmark
  follows the same semantics: it clears the tokenizer text cache before every
  timed repetition (warmup only loads the tokenizer and reaches steady
  state), so published wall times are cold-cache numbers.
- The Docker production image now installs a built wheel instead of an
  editable source link, drops the `uv` binary and source tree from the
  runtime stage, and bakes the frontend into the installed package. Build
  scripts pass a `COMMIT` build argument so `GET /version` reports the
  deployed revision, and `docker-compose.yml` healthchecks `GET /health`
  instead of the SPA root.
- The Web UI's default splitter is now `section`, matching the documented
  CLI/Web/Python default instead of `sibling`.
- HTML parsing now retains text that was previously dropped: fragments without
  `<body>` wrappers, bare text between constructs, nested list items inside
  their parent item, unclosed headings/lists/tables/paragraphs flushed at end
  of input, `<dt>`/`<dd>`/`<div>`-style block boundaries keeping adjacent words
  separate, and implied end tags such as `<h1>a<h2>b`, `<li>x<li>y`, and any
  `</hN>` closing an open heading.
- CSV/TSV parsing now preserves RFC 4180 quoted fields containing embedded
  newlines and delimiters instead of silently dropping the newlines and
  shifting row provenance.
- SQL parsing now splits statements on a quote/comment-aware scanner, so
  semicolons inside `'...'`, `"..."`, backtick identifiers, `$$...$$` dollar
  quotes, `--`, and `/* */` comments no longer break a statement, and
  comment-only tails emit no records.
- XML parsing now retains mixed-content `text()`/tail segments (for example
  `<root>lead<b>bold</b>tail</root>`) as ordered records instead of dropping
  the container text.
- Invalid TOML input is now consistently rejected with `ValueError` like JSON
  and YAML instead of leaking `tomllib.TOMLDecodeError`.
- Added a parser-focused large-corpus benchmark with version-pinned Markdown
  and DOCX sources, deterministic per-source random sampling, per-document raw
  evidence, token/character content-retention metrics, element conformance
  assertions, structure validation, and error distributions.
- Added versioned v1 JSON schemas and shared serializers for chunks and document
  trees. CLI and Web split results now include `schema_version`.
- Added streaming `Lumberjack.saw_many()` with per-document success or failure
  records, plus directory/glob JSONL CLI processing and safe output-directory
  writes.
- Added explicit `Lumberjack.trace()` pipeline traces, format-neutral source
  locations, optional parser extraction results, and source-location metadata
  on chunks across Python, CLI, and Web outputs.
- Added `DocTreeBuilder` for supported construction of hierarchical or flat
  parser output without requiring synthetic headings, plus explicit record
  topology and `RecordSplitter` for atomic row/record packing.
- Added UTF-8 TXT/LOG, CSV/TSV, and JSONL parsing with explicit row, line, and
  JSON-path provenance. Use the `record` splitter for LOG, CSV/TSV, and JSONL
  inputs so records remain atomic.
- Added JSON, YAML, and XML parsing as ordered scalar or leaf-element records
  with key or element paths and scalar-type metadata.
- Added optional XLSX parsing with sheet, row, column, and header provenance;
  install the `spreadsheets` extra to enable it.
- Added optional Tree-sitter source parsing for Python, JavaScript/TypeScript,
  Bash, C/C++, C#, Go, Java, Kotlin, Lua, PHP, Ruby, Rust, Swift, and Zig
  declarations, including byte and line provenance and recovery from malformed
  source; install the `code-parsing` extra to enable it.
- Added a reproducible benchmark MVP with a versioned public corpus, quality
  and performance metrics, raw-result JSON, and optional competitor adapters.
- Added a MkDocs Material documentation site with getting-started, concepts,
  configuration, custom-component, CLI, Web API, and generated Python API
  reference pages.

### Changed

- **Breaking:** Consolidated CLI block configuration into the repeatable compact
  `--block KIND:SETTING,...` option, and grouped generated CLI help by task.
- **Breaking:** The default splitter is now `section` across the Python API, CLI, and Web API. Select `sibling` explicitly when adjacent sibling sections should be packed together.
- Streamlined the English and Chinese READMEs around installation, a first split,
  splitter selection, and links to the complete documentation.

### Fixed

- Seeded XLSX corpus generation is now byte-deterministic across runs: the
  generator pins the workbook's creation and modification timestamps instead
  of letting openpyxl stamp wall-clock times, which previously made the same
  seed produce different archives when generation straddled a second
  boundary.
- DOCX parsing now preserves hyperlinks and embedded images as inline nodes,
  including inside tables; recognizes direct OOXML numbering; groups consecutive
  list items; reads visible content controls and tracked insertions; and escapes
  Markdown table delimiters and multiline cells. DOCX provenance now uses OOXML
  element paths instead of synthetic line numbers.
- Markdown math parsing now distinguishes currency-shaped dollar text, supports
  numbered dollar/bracket display formulas, retains delimiter information, and
  does not consume trailing prose after an invalid bracket-math block form.
- DOCX parsing now recognizes linear OMML math, wrapped table cells, and visible
  text boxes, and tolerates Strict OOXML plus narrowly repairable package
  metadata defects while recording applied repairs.
- DOCX headings and lists now rely only on explicit OOXML outline/numbering
  properties; style names and monospace appearance are no longer guessed as
  heading, list, quote, or code semantics. Ambiguous or oversized OPC packages
  are rejected before parsing.

## [0.4.0] - 2026-08-19

### Added

- Added the real `ChunkFinalizer`, `TextNormalizer`, and `TextTransformer` stages. Splitter implementations now return unfinished `ChunkDraft` objects; `ChunkFinalizer` renders and post-processes them, performs authoritative final measurement, and produces `Chunk` objects.
- Added opt-in `PlainTextTransformer` for removing common Markdown and HTML surface syntax. The default TextNormalizer and TextTransformer only normalize line endings, BOM/NUL characters, and repeated blank separators.
- Added `SplitResult`, which returns the parsed `DocTree` together with final chunks so document metadata and Markdown reference definitions remain available after splitting.

### Changed

- PyPI distribution name is now `lumberjack-py`; Python imports and CLI commands remain `lumberjack` and `lumber`.
- **Breaking:** Replaced the top-level `lumber()` function with `Lumberjack(...).saw(...)` and the explicit `Document -> DocTree -> ChunkDraft -> Chunk` pipeline. The package root now exports only `Lumberjack` and `Document`.
- **Breaking:** Replaced lumber-themed component names with `Parser.parse()`, `Tokenizer.count()`, and `Splitter.split()`. The old `lumberjack.feller`, `lumberjack.sawyer`, and `lumberjack.scaler` paths are removed without compatibility aliases.
- CLI and Web request fields remain `tokenizer` and `splitter`; their private adapter now maps those integration names to Tokenizer and Splitter implementations.
- `SectionSplitter` applies `merge_below_ratio` bottom-up to adjacent same-heading text tails produced while splitting oversized blocks, without subtree collapse or non-text draft merging.
- **Breaking:** Chunk headings are now separated into `ancestor_headings` and an optional singular `own_heading`; external headings are never rendered in `body`, while headings for merged internal sections remain in the body.
- **Breaking:** Replaced `render_headings` with `heading_sensitive`, which controls whether external heading tokens count toward split budgets. Chunks now report separate `headings_token_count` and `body_token_count`; `token_count` also includes `tokenizer.count("\n\n")` for the separator between them.
- **Breaking:** `Lumberjack.saw()` and the private CLI/Web pipeline now return `SplitResult` instead of a bare chunk list. CLI and Web JSON responses include document `metadata` and `reference_definitions`.
- Web requests reuse expensive tokenizer model backends while retaining an independent LRU text cache for each request.
- Oversized-text fallback uses bounded prefix searches and avoids packing fallback levels containing an already-oversized atomic part.
- Wheel and source distributions do not bundle the Web UI's static build output (`lumberjack/web/static`); build it from `lumberjack_webui/` when serving the UI locally. The Docker image builds the frontend in its own stage and is unaffected.
- The Web UI toolchain now uses bun instead of npm: `lumberjack_webui/bun.lock` replaces `package-lock.json`, and CI, the Docker build, and documentation run frontend commands with bun (`bun install --frozen-lockfile`, `bun run lint`, `bun run build`).

### Fixed

- Default Markdown post-processing now preserves trailing whitespace, including hard line breaks and whitespace in fenced code blocks.
- Split-time budgets now include the tokenized separator between external headings and chunk bodies, matching final `Chunk.token_count` calculations.
- Web budget parameters now have request-boundary validation, and invalid input or unavailable requested tokenizer dependencies return client errors instead of internal-server details.

## [0.3.0] - 2026-07-22

### Added

- Added component-oriented public modules and packages: `lumberjack.parser`, `lumberjack.splitter`, `lumberjack.tokenizer`, `lumberjack.block`, `lumberjack.models`, and `lumberjack.protocols`.
- Added `AutoParser` with suffix, DOCX structure, and HTML content detection; all parser objects now share `metadata_overrides` and `source_path` document arguments.
- Added typed block configuration with `BlockKind`, `BlockConfig`, table-specific configs, and `CustomBlockConfig`.

### Changed

- **Breaking:** `lumber()` is now a minimal convenience API accepting only `source`, `format`, and `max_tokens`; advanced use is composed explicitly from parser, tokenizer, and splitter objects.
- **Breaking:** Unprefixed `SiblingSplitter`, `SubtreeSplitter`, and `SectionSplitter` classes and CLI/Web names now use incremental measurement. Full recounting is selected through explicit `Exact*Splitter` classes or `exact-*` integration names.
- **Breaking:** Splitters accept validated constructor arguments directly. `SectionSplitter` no longer exposes the inapplicable `merge_below_ratio` argument.
- **Breaking:** `MarkdownParser` now disables Setext headings by default; pass `disable_lheading=False` to enable them.
- **Breaking:** The public AST node types are now format-neutral: `MarkdownInline` and `MarkdownBlock` were renamed to `DocumentInline` and `DocumentBlock`. Their text is defined as canonical Markdown-like rendered content rather than a guaranteed source slice.
- **Breaking:** The default `approx` tokenizer now estimates tokens as UTF-8 bytes ÷ 3 (3 bytes per token) instead of characters ÷ 4, producing more accurate estimates for mixed ASCII/CJK text. This shifts chunk boundaries produced with the default tokenizer. The public class was renamed from `ApproxCharTokenizer` to `ApproxByteTokenizer` to reflect the new behavior.
- **Breaking:** Tokenizers are no longer thread-safe. The `RLock` guarding `TiktokenTokenizer`/`TransformersTokenizer` caches was removed to match the single-threaded contract used by the rest of the library; do not share a single tokenizer instance across threads.
- `TransformersTokenizer` now mirrors `TiktokenTokenizer`: it gained the `default_cache` constructor parameter and uses `cachetools.LRUCache` for its cache instead of a hand-rolled `OrderedDict` LRU. Both tokenizers now share the same `default_cache`/`cache` semantics.
- `DocTree.source_path` now records source provenance independently, and `Chunk.document_path` is generated from that field rather than semantic metadata.
- Public parser, splitter, tokenizer, block, model, and protocol namespaces now own their implementations directly instead of forwarding to a parallel `core` tree.
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
