# lumberjack Development Notes

## Project

The project is in the **development stage** and compatibility does not need to be considered. Allow all disruptive changes.

Markdown / HTML / DOCX document splitter for RAG preprocessing. Python 3.10+, `src/` layout, built with `hatchling` + `hatch-vcs`.

Current runtime dependencies:

- `markdown-it-py[linkify,plugins]>=4.0.0` for the default GFM-like parser
- `pyyaml>=6.0` for YAML front matter parsing

Optional dependencies:

- `tiktoken>=0.9.0`, `cachetools>=7.1.1` for model-based token counting (install via `--extra tokenizers`)
- `python-docx>=1.1.0` for DOCX document support (install via `--extra docx`)
- `fastapi>=0.115.0`, `uvicorn>=0.34.0`, `python-multipart>=0.0.18` for the web server (install via `--extra web`)

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

# Show CLI help
uv run lumber --help

# Run web server (development)
uv run lumberjack-serve --reload

# Run web server (production)
uv run lumberjack-serve --host 0.0.0.0 --port 8000

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
Tree -> Feller.fell() -> Log -> Sawyer.saw() -> Bundle[]
     -> Mill.mill() -> Seasoner -> Planer -> Chunk[]
```

All three formats produce the same `Log` (with `SectionNode` tree and `DocumentBlock` children), so all sawyers work with any format. Public component namespaces own their implementations directly; the removed parser/splitter/tokenizer/core paths have no compatibility aliases.

Main components:

### Shared public modules

- **Models**: `src/lumberjack/models.py`
  - `Tree` — raw input plus format, title, metadata overrides, and provenance
  - `DocumentInline`, `DocumentBlock`, `SectionNode`, `Log` — shared across formats
  - `Bundle` — internal output of sawing; `Chunk` — final output of milling
- **Protocols**: `src/lumberjack/protocols.py`
  - `ScalerProtocol`, `FellerProtocol`, `SawyerProtocol`, `SeasonerProtocol`, `PlanerProtocol`
- **Scaler**: `src/lumberjack/scaler.py`
  - `ApproxByteScaler` (default, estimates tokens as UTF-8 bytes ÷ 3), `TiktokenScaler` and `TransformersScaler` (optional)
- **Block configuration**: `src/lumberjack/block.py`
  - `BlockKind`, `BlockConfig`, `MarkdownTableConfig`, `HTMLTableConfig`, and `CustomBlockConfig`
  - Python `block_options` accepts a sequence of these objects; CLI/Web adapters convert their external mapping formats at the boundary
- **Sawyers**: `src/lumberjack/sawyer/` — public implementations operating on `Log`, format-agnostic
  - `base.py` provides `BaseSawyer` shared state and helpers
  - `sibling.py` provides `SiblingSawyer` — structure-first, budget-aware sibling packing
  - `subtree.py` provides `SubtreeSawyer` — subtree-first collapse with section fallback
  - `section.py` provides `SectionSawyer` — direct-body recursion with no subtree collapse
  - Unprefixed class names use incremental counting and `Exact*Sawyer` names use full recounting
- **Mill stages**: `mill.py`, `seasoner.py`, and `planer.py`
  - `Mill` renders bundles, applies `Seasoner` then `Planer`, performs authoritative counts, and emits chunks
  - `PlainTextPlaner` is opt-in; default stages preserve Markdown surface syntax
- **Private helpers**: `src/lumberjack/_internal/`
  - `block_saw.py` handles oversized blocks, `options.py` converts CLI/Web block configuration, `formats.py` detects integration input formats, `pipeline.py` orchestrates CLI/Web components, and `rendering.py` contains shared rendering helpers

### Fellers (`src/lumberjack/feller/`)

Format-specific fellers — each turns one input format into the shared `Log`.

#### Markdown (`src/lumberjack/feller/markdown/`)

- **Feller**: `src/lumberjack/feller/markdown/feller.py`
  - `MarkdownFeller` aliases `MarkdownItFeller`
  - Uses `MarkdownIt("gfm-like")` with built-in plugins
  - `MarkdownItFeller(disable_lheading=True)` to disable Setext heading parsing
  - Parses YAML front matter, preserves heading hierarchy, inlines, reference definitions, line ranges
- **Plugins**: `src/lumberjack/feller/markdown/plugins/`
  - `brackets_math_plugin`: `\[...\]` block math and `\(...\)` inline math syntax

#### DOCX (`src/lumberjack/feller/docx/`)

- **Feller**: `src/lumberjack/feller/docx/feller.py`
  - `DocxFeller` — fells DOCX into `Log`
  - Maps Heading styles -> `SectionNode`, paragraphs -> `paragraph`, tables -> `table`, lists -> `list`, etc.
  - Iterates body elements in document order to preserve paragraph/table sequence
  - Extracts core properties as document metadata

#### HTML (`src/lumberjack/feller/html/`)

- **Feller**: `src/lumberjack/feller/html/feller.py`
  - `HTMLFeller` — fells HTML into `Log`, mirroring Markdown and DOCX fellers
  - Built on stdlib `html.parser.HTMLParser` (aliased internally as `_StdlibHTMLParser` to avoid name shadowing)
  - `_HTMLDocumentBuilder` is the event-driven internal builder
  - Maps headings -> `SectionNode`, paragraphs -> `paragraph`, tables -> `html_table`, lists -> `list`, etc.
- **Table utility**: `src/lumberjack/feller/html/table_parser.py`
  - `HTMLTableParser` + `HTMLTable`/`HTMLTableRow`/`HTMLTableCell` dataclasses
  - Consumed by the Markdown feller and `block_saw.py`; not used by `HTMLFeller` itself

### Public API

- `src/lumberjack/__init__.py` — exports only `Lumberjack` and `Tree`
- `src/lumberjack/feller/` — `AutoFeller`, concrete fellers, and Markdown plugin extensions
- `src/lumberjack/sawyer/` — default incremental sawyers and explicit `Exact*Sawyer` classes
- `src/lumberjack/scaler.py` — scaler implementations
- `src/lumberjack/mill.py`, `seasoner.py`, `planer.py` — final processing stages
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

Implemented in `src/lumberjack/web/`.

- `POST /lumber/api/split/text` — JSON body with `text` and split options
- `POST /lumber/api/split/file` — multipart form with `file` upload and split options
  - Supports `input_format` form field (`"auto"`, `"markdown"`, `"html"`, `"docx"`)
  - Auto-detects format from file extension when `"auto"`
- Response: JSON with `document`, `chunk_count`, and `chunks` array
- Server CLI: `lumberjack-serve` with `--host`, `--port`, `--reload`

## CLI Behavior

Implemented in `src/lumberjack/cli.py`.

- Input is a Markdown (`.md`), HTML (`.html`), or DOCX (`.docx`) file path
- `--input-format`: `auto` (detect from extension), `markdown`, `html`, or `docx`
- Output format: JSON only
- Tokenizers (engine): `approx`, `tiktoken`, `transformers`
- Exact vs incremental counting is a property of the sawyer class, not the scaler. CLI/Web retain their existing `splitter` and `tokenizer` field names as an integration protocol.
- Splitter choices: `sibling` (default, incremental), `subtree` (incremental), `section` (incremental), `exact-sibling`, `incremental-sibling`, `exact-subtree`, `incremental-subtree`, `exact-section`, `incremental-section`
- `--block-config KIND[:isolated][:nosplit][:TOKENS]` per-block-kind config; repeatable
- JSON output serializes dataclasses with `dataclasses.asdict`

## Splitting Rules

- Whole document is kept as one chunk when it already fits the budget
- `SiblingSawyer` (default): merges adjacent sibling sections when they fit within `max_tokens`
- `SubtreeSawyer`: subtree-first collapse. `SectionSawyer`: always per-heading with no subtree-collapse.
- Tail-fragment merging (`merge_below_ratio`, default `0.125`): bottom-up, merges same-heading adjacent `paragraph` chunks whose tail is below `int(max_tokens * ratio)` tokens, when the merged result fits `max_tokens`. Disabled when `ratio == 0`. In the `section` splitter this runs only within each section's direct-body drafts, so it cannot collapse subtrees or merge non-text block chunks.
- Text fallback order is paragraph break -> line break -> sentence -> word -> hard split
- `Chunk.body` always includes rendered heading context; shared parent headings are deduplicated
- `skip_empty_sections=True` discards chunks that contain only a heading with no body content
- `block_options` is a sequence of typed objects from `lumberjack.block`; duplicate kinds are rejected
- Exact `Exact*Sawyer` classes fully recount rendered text at every budget decision. Default unprefixed sawyers use a running additive estimate. `Mill` performs the authoritative final recount after seasoning and planing.

## Constraints

- Markdown, HTML, and DOCX are the supported input formats
- Fenced code blocks are preserved intact even when they exceed `max_tokens` (unless `code_block`/`code_fence` has `split=True`)
- CLI should stay orchestration-only; parsing and splitting logic belongs to the public component implementations, while integration adapters belong in `src/lumberjack/_internal/`
- There is no LangChain dependency

## Testing

Tests use `pytest`. `tests/conftest.py` adds `src/` to `sys.path`.

Current test areas:

- Markdown feller heading-tree construction, inlines, line ranges
- DOCX feller heading parsing, table extraction, list detection, section tree structure
- Section-aware chunking, budget management, merging
- Public `Lumberjack.saw()` API with Markdown and DOCX input
- Web API split with text input, file upload, error handling, and full options

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

## Code Organization

```
src/lumberjack/
    __init__.py                     # Public API: Lumberjack, Tree
    lumberjack.py                   # Full pipeline orchestrator
    cli.py                          # CLI orchestration
    block.py                        # Public block kinds and typed configuration
    models.py                       # Public shared data models
    protocols.py                    # Public extension protocols
    scaler.py                       # Public scaler implementations
    mill.py                         # Bundle-to-Chunk finishing stage
    seasoner.py                     # Text stabilization stage
    planer.py                       # Text normalization/plain-text stages
    web/                            # FastAPI layer
    feller/                         # Public feller implementations
        __init__.py                 # AutoFeller and concrete feller exports
        auto.py                     # Format inference and feller selection
        markdown/
            feller.py               # MarkdownItFeller
            plugins/                # markdown-it plugins
        docx/
            feller.py               # DocxFeller
        html/
            feller.py               # HTMLFeller + _HTMLDocumentBuilder
            table_parser.py         # HTMLTableParser + HTMLTable*
    sawyer/                         # Public sawyer implementations
        base.py
        exact.py
        incremental.py
        sibling.py
        subtree.py
        section.py
        topology/
    _internal/                      # Private cross-component helpers
        block_saw.py
        formats.py
        options.py
        pipeline.py
        rendering.py
lumberjack_webui/                   # React + TypeScript frontend
tests/                              # mirrors src/lumberjack layout
    __init__.py
    conftest.py
    helpers.py                     # shared test helpers (FIXTURES_DIR, etc.)
    test_api.py                    # tests package API and built-in components
    test_cli.py                    # tests src/lumberjack/cli.py
    test_docker.py                 # tests docker/Dockerfile
    parser/                        # historical test folder; covers src/lumberjack/feller/
        markdown/test_markdown_parser.py
        docx/test_docx_parser.py
        html/test_html_parser.py
        html/test_table_integration.py
    splitter/                      # historical test folder; covers src/lumberjack/sawyer/
        test_splitter.py
        test_render_headings.py
        test_max_heading_level.py
        test_token_counting_modes.py
    web/test_web.py                # tests src/lumberjack/web/
    _internal/test_rendering.py    # tests src/lumberjack/_internal/rendering.py
    contracts/                     # public-API contract tests
        test_cli_contract.py
        test_public_api_contract.py
        test_web_contract.py
    fixtures/
        markdown/
        docx/
```
