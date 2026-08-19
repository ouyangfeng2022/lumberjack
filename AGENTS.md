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

All three formats produce the same `DocTree` (with `SectionNode` tree and `DocumentBlock` children), so all splitters work with any format. Public component namespaces own their implementations directly; the removed feller/sawyer/scaler/core paths have no compatibility aliases.

Main components:

### Shared public modules

- **Models**: `src/lumberjack/models.py`
  - `Document` — raw input plus format, title, metadata overrides, and provenance
  - `DocumentInline`, `DocumentBlock`, `SectionNode`, `DocTree` — shared across formats
  - `ChunkDraft` — internal output of sawing; `Chunk` — final output of finalizeing
- **Protocols**: `src/lumberjack/protocols.py`
  - `TokenizerProtocol`, `ParserProtocol`, `SplitterProtocol`, `TextNormalizerProtocol`, `TextTransformerProtocol`
- **Tokenizer**: `src/lumberjack/tokenizer.py`
  - `ApproxByteTokenizer` (default, estimates tokens as UTF-8 bytes ÷ 3), `TiktokenTokenizer` and `TransformersTokenizer` (optional)
- **Block configuration**: `src/lumberjack/block.py`
  - `BlockKind`, `BlockConfig`, `MarkdownTableConfig`, `HTMLTableConfig`, and `CustomBlockConfig`
  - Python `block_options` accepts a sequence of these objects; CLI/Web adapters convert their external mapping formats at the boundary
- **Splitters**: `src/lumberjack/splitter/` — public implementations operating on `DocTree`, format-agnostic
  - `base.py` provides `BaseSplitter` shared state and helpers
  - `sibling.py` provides `SiblingSplitter` — structure-first, budget-aware sibling packing
  - `subtree.py` provides `SubtreeSplitter` — subtree-first collapse with section fallback
  - `section.py` provides `SectionSplitter` — direct-body recursion with no subtree collapse
  - Unprefixed class names use incremental counting and `Exact*Splitter` names use full recounting
- **ChunkFinalizer stages**: `finalize.py`, `normalizer.py`, and `transformer.py`
  - `ChunkFinalizer` renders drafts, applies `TextNormalizer` then `TextTransformer`, performs authoritative counts, and emits chunks
  - `PlainTextTransformer` is opt-in; default stages preserve Markdown surface syntax
- **Private helpers**: `src/lumberjack/_internal/`
  - `block_saw.py` handles oversized blocks, `options.py` converts CLI/Web block configuration, `formats.py` detects integration input formats, `pipeline.py` orchestrates CLI/Web components, and `rendering.py` contains shared rendering helpers

### Parsers (`src/lumberjack/parser/`)

Format-specific parsers — each turns one input format into the shared `DocTree`.

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
  - Consumed by the Markdown parser and `block_saw.py`; not used by `HTMLParser` itself

### Public API

- `src/lumberjack/__init__.py` — exports only `Lumberjack` and `Document`
- `src/lumberjack/parser/` — `AutoParser`, concrete parsers, and Markdown plugin extensions
- `src/lumberjack/splitter/` — default incremental splitters and explicit `Exact*Splitter` classes
- `src/lumberjack/tokenizer.py` — tokenizer implementations
- `src/lumberjack/finalize.py`, `normalizer.py`, `transformer.py` — final processing stages
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
- Exact vs incremental counting is a property of the splitter class, not the tokenizer. CLI/Web retain their existing `splitter` and `tokenizer` field names as an integration protocol.
- Splitter choices: `sibling` (default, incremental), `subtree` (incremental), `section` (incremental), `exact-sibling`, `incremental-sibling`, `exact-subtree`, `incremental-subtree`, `exact-section`, `incremental-section`
- `--block-config KIND[:isolated][:nosplit][:TOKENS]` per-block-kind config; repeatable
- JSON output serializes dataclasses with `dataclasses.asdict`

## Splitting Rules

- Whole document is kept as one chunk when it already fits the budget
- `SiblingSplitter` (default): merges adjacent sibling sections when they fit within `max_tokens`
- `SubtreeSplitter`: subtree-first collapse. `SectionSplitter`: always per-heading with no subtree-collapse.
- Tail-fragment merging (`merge_below_ratio`, default `0.125`): bottom-up, merges same-heading adjacent `paragraph` chunks whose tail is below `int(max_tokens * ratio)` tokens, when the merged result fits `max_tokens`. Disabled when `ratio == 0`. In the `section` splitter this runs only within each section's direct-body drafts, so it cannot collapse subtrees or merge non-text block chunks.
- Text fallback order is paragraph break -> line break -> sentence -> word -> hard split
- `Chunk.body` always includes rendered heading context; shared parent headings are deduplicated
- `skip_empty_sections=True` discards chunks that contain only a heading with no body content
- `block_options` is a sequence of typed objects from `lumberjack.block`; duplicate kinds are rejected
- Exact `Exact*Splitter` classes fully recount rendered text at every budget decision. Default unprefixed splitters use a running additive estimate. `ChunkFinalizer` performs the authoritative final recount after seasoning and planing.

## Constraints

- Markdown, HTML, and DOCX are the supported input formats
- Fenced code blocks are preserved intact even when they exceed `max_tokens` (unless `code_block`/`code_fence` has `split=True`)
- CLI should stay orchestration-only; parsing and splitting logic belongs to the public component implementations, while integration adapters belong in `src/lumberjack/_internal/`
- There is no LangChain dependency

## Testing

Tests use `pytest`. `tests/conftest.py` adds `src/` to `sys.path`.

Current test areas:

- Markdown parser heading-tree construction, inlines, line ranges
- DOCX parser heading parsing, table extraction, list detection, section tree structure
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

## Code Organization

```
src/lumberjack/
    __init__.py                     # Public API: Lumberjack, Document
    lumberjack.py                   # Full pipeline orchestrator
    cli.py                          # CLI orchestration
    block.py                        # Public block kinds and typed configuration
    models.py                       # Public shared data models
    protocols.py                    # Public extension protocols
    tokenizer.py                       # Public tokenizer implementations
    finalize.py                         # ChunkDraft-to-Chunk finishing stage
    normalizer.py                     # Text stabilization stage
    transformer.py                       # Text normalization/plain-text stages
    web/                            # FastAPI layer
    parser/                         # Public parser implementations
        __init__.py                 # AutoParser and concrete parser exports
        auto.py                     # Format inference and parser selection
        markdown/
            parser.py               # MarkdownItParser
            plugins/                # markdown-it plugins
        docx/
            parser.py               # DocxParser
        html/
            parser.py               # HTMLParser + _HTMLDocumentBuilder
            table_parser.py         # HTMLTableParser + HTMLTable*
    splitter/                         # Public splitter implementations
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
    parser/                        # historical test folder; covers src/lumberjack/parser/
        markdown/test_markdown_parser.py
        docx/test_docx_parser.py
        html/test_html_parser.py
        html/test_table_integration.py
    splitter/                      # historical test folder; covers src/lumberjack/splitter/
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
