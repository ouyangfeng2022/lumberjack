# Controllable Heading Rendering For Chunks

## Summary
Add a public `render_headings: bool = True` option. Default behavior stays current: `Chunk.body` includes rendered heading paths. When `render_headings=False`, `Chunk.body` contains no Markdown headings at all, while `Chunk.headings` keeps the current single common `HeadingPath` metadata for the chunk.

## Key Changes
- Add `render_headings` to `SplitOptions`, `lumber()`, CLI, FastAPI text/file endpoints, React option state, API payloads, and README/README.zh-CN docs.
- CLI exposes this as `--render-headings` / `--no-render-headings`, defaulting to `--render-headings`.
- Web UI adds an advanced checkbox labeled “Render headings” / “渲染标题”; result cards still show the breadcrumb from `chunk.headings`.

## Core Implementation
- Implement the behavior in `_BaseSplitter`, not in `RecursiveSplitter` or `SectionSplitter`, because final body rendering and finalization are shared.
- When `render_headings=False`:
  - `_render_body()` joins only rendered entry bodies and never calls `render_heading_path()`.
  - heading token counts used by drafts, subtree estimates, child packing, merge checks, and final `estimated_token_count` become `0`.
  - `_measure_section()` should not add title tokens or heading tail text, so split decisions are based on the body that will actually be rendered.
- Keep `Chunk.headings = common_heading_path(entry.headings for entry in chunk.entries)` unchanged; no response schema change and no per-entry path list.

## Test Plan
- Add splitter tests for:
  - default behavior still renders heading paths.
  - `render_headings=False` returns body-only chunks but preserves `headings`.
  - hidden headings are excluded from `estimated_token_count` and budget decisions.
  - merged sibling chunks with hidden headings keep the current common `headings` path.
- Add API/web tests for `lumber(render_headings=False)`, `/split/text`, and `/split/file`.
- Add CLI parser or smoke coverage for `--no-render-headings`.
- Run:
  - `uv run pytest tests/test_splitter.py tests/test_api.py tests/test_web.py -q`
  - `uv run ty check .`
  - `uv run ruff check --fix`
  - `uv run ruff format`
  - `uv run pytest -q`
  - `npm run lint` and `npm run build` in `lumberjack_webui`

## Assumptions
- `render_headings=True` remains the default.
- `render_headings=False` removes all headings from `Chunk.body`, including the chunk’s own heading.
- `Chunk.headings` remains the existing single common path, not a new multi-path schema.
