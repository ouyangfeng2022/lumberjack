# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Changed

- Constrained the web dependency set to Starlette versions before 1.0 so FastAPI test clients continue to process requests.
- Renamed the section-family splitters so class and registry names describe their actual behavior. The subtree-first splitter (formerly `SectionSplitter`, registry `section`/`exact-section`/`incremental-section`) is now `SubtreeSplitter` with registry `subtree`/`exact-subtree`/`incremental-subtree`. The per-heading splitter (formerly `SectionFlatSplitter`, registry `section-flat`/`exact-section-flat`/`incremental-section-flat`) is now `SectionSplitter` with registry `section`/`exact-section`/`incremental-section`.
- `max_heading_level` is now applied by splitters, so parsers preserve the full heading tree while deeper headings render as chunk body text.

### Removed

- `SectionFlatSplitter`, `ExactSectionFlatSplitter`, and `IncrementalSectionFlatSplitter` aliases and the `section-flat`/`exact-section-flat`/`incremental-section-flat` registry names. Use the renamed `SectionSplitter` (registry `section`) instead. The previous subtree-first `SectionSplitter`/`ExactSectionSplitter`/`IncrementalSectionSplitter` names are now `SubtreeSplitter`/`ExactSubtreeSplitter`/`IncrementalSubtreeSplitter`.

### Added

- Structure-aware Markdown splitting with recursive and section strategies
- GFM-like parser with LaTeX math (dollarmath), YAML front matter, and bracket math plugins
- CLI entry point: `lumber`
- Web server entry point: `lumberjack-serve`
- Python API: `lumberjack.lumber()`
- Simple character and tiktoken tokenizer implementations
- FastAPI web server with React frontend
- PEP 561 type marker (`py.typed`)
