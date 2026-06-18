# Splitter Organization Design

## Goal

Reorganize the document-level splitter implementation so each module has a clear
responsibility. The project is in active development, so old import paths do not
need compatibility shims. The refactor must preserve splitter behavior.

## Current Shape

`src/lumberjack/core/splitter.py` currently contains shared draft data models,
heading helpers, base splitter behavior, both splitter strategies, and the
registry/factory. This makes the file large and makes future splitter changes
harder to localize.

`src/lumberjack/core/text_splitter.py` handles oversized block splitting for
text, code, lists, Markdown tables, and HTML tables. Its responsibility is
different from document-level splitter strategies, so it stays outside the new
package.

## Target Structure

Create a new package:

```text
src/lumberjack/core/splitters/
    __init__.py
    base.py
    drafts.py
    headings.py
    recursive.py
    registry.py
    section.py
```

Responsibilities:

- `drafts.py`: `_Entry`, `_ChunkDraft`, `_SectionTokenCounts`, and
  `_MeasuredSection`.
- `headings.py`: `render_heading_path()` and `common_heading_path()`.
- `base.py`: `_BaseSplitter`, shared measuring, section-body splitting,
  finalization, rendering, and merge helpers.
- `recursive.py`: `RecursiveSplitter`.
- `section.py`: `SectionSplitter`.
- `registry.py`: `SPLITTER_REGISTRY` and `create_splitter()`.
- `__init__.py`: public exports for the splitter package.

Remove the old `src/lumberjack/core/splitter.py` module after all internal and
test imports are migrated.

## Import Policy

Preferred public import:

```python
from lumberjack.core.splitters import RecursiveSplitter, SectionSplitter, create_splitter
```

Internal modules may import from specific submodules when that keeps
dependencies clear, for example:

```python
from lumberjack.core.splitters.drafts import _ChunkDraft
from lumberjack.core.splitters.headings import common_heading_path
```

Tests should use the same new paths. No compatibility layer should remain for
`lumberjack.core.splitter`.

## Behavior Constraints

This is a structural refactor only.

- Do not change chunk boundaries.
- Do not change token estimates.
- Do not change public splitter names: `default`, `recursive`, and `section`.
- Do not change `SplitOptions`.
- Do not move `TextSplitter` into the splitter package in this pass.
- Preserve DOCX and Markdown sharing the same `DocumentAST` pipeline.

## Documentation Updates

Update references to the old splitter file in project documentation:

- `AGENTS.md`
- `README.md` if it mentions the old splitter module path
- Other docs found by grep that describe splitter file organization

The docs should describe the new `core/splitters/` package and keep
`core/text_splitter.py` documented as the oversized-block fallback splitter.

## Testing

Run focused splitter checks first, then the broader Python checks:

```bash
uv run pytest tests/test_splitter.py -q
uv run ruff check --fix
uv run ruff format
uv run ruff check
uv run pytest -q
```

If docs-only import references are changed, no separate frontend checks are
needed. If the refactor unexpectedly touches web UI code, add the web UI lint
and build checks.

## Risks

The main risk is missing an old import of `lumberjack.core.splitter`. Use `rg`
to find and migrate all references before deleting the old module.

The second risk is circular imports between `base.py`, `recursive.py`,
`section.py`, and `registry.py`. Keep strategy modules dependent on base helpers,
and keep the registry as the only module that imports both concrete strategies.

The third risk is accidental behavior drift while moving helper code. Minimize
manual edits during the move and rely on the existing splitter tests as the
behavior safety net.
