# Splitter Organization Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Split the large document-level splitter module into a focused `core/splitters/` package while preserving current behavior.

**Architecture:** Move pure shared data and helper functions first, then move `_BaseSplitter`, concrete splitter strategies, and the registry. Delete the old `core/splitter.py` module after all imports are migrated because the project does not require compatibility shims.

**Tech Stack:** Python 3.13, `dataclasses`, existing Lumberjack core models/protocols/tokenizers, pytest, ruff.

---

## File Structure

- Create: `src/lumberjack/core/splitters/__init__.py`
  - Public package exports for `RecursiveSplitter`, `SectionSplitter`, `SPLITTER_REGISTRY`, `create_splitter`, and heading helpers.
- Create: `src/lumberjack/core/splitters/drafts.py`
  - Internal dataclasses: `_Entry`, `_ChunkDraft`, `_SectionTokenCounts`, `_MeasuredSection`.
- Create: `src/lumberjack/core/splitters/headings.py`
  - Heading-path rendering and common-prefix helpers.
- Create: `src/lumberjack/core/splitters/base.py`
  - `_BaseSplitter` plus shared measuring, body splitting, draft merging, rendering, and finalization logic.
- Create: `src/lumberjack/core/splitters/recursive.py`
  - `RecursiveSplitter`.
- Create: `src/lumberjack/core/splitters/section.py`
  - `SectionSplitter`.
- Create: `src/lumberjack/core/splitters/registry.py`
  - `SPLITTER_REGISTRY` and `create_splitter()`.
- Delete: `src/lumberjack/core/splitter.py`
  - Remove the old module after all imports are migrated.
- Modify: `src/lumberjack/core/__init__.py`
  - Import splitter exports from `core.splitters`.
- Modify: tests importing `lumberjack.core.splitter`
  - Use `lumberjack.core.splitters` or specific submodules.
- Modify: documentation that mentions `core/splitter.py`
  - Update to `core/splitters/` and keep `core/text_splitter.py` documented separately.

---

### Task 1: Establish Baseline and Create Splitter Package Shell

**Files:**
- Create: `src/lumberjack/core/splitters/__init__.py`
- Test: `tests/test_splitter.py`

- [ ] **Step 1: Run current splitter tests as the refactor baseline**

Run:

```bash
uv run pytest tests/test_splitter.py -q
```

Expected: tests pass, or any existing unrelated failure is recorded before code
changes. If this command fails because the deleted fixture
`tests/fixtures/markdown/deep-research-report.md` affects the suite, do not
restore or modify that user change; record the failure and continue with the
most focused unaffected splitter tests.

- [ ] **Step 2: Create the package export shell**

Create `src/lumberjack/core/splitters/__init__.py` with this temporary content:

```python
from .registry import SPLITTER_REGISTRY, create_splitter
from .recursive import RecursiveSplitter
from .section import SectionSplitter
from .headings import common_heading_path, render_heading_path

__all__ = [
    "RecursiveSplitter",
    "SPLITTER_REGISTRY",
    "SectionSplitter",
    "common_heading_path",
    "create_splitter",
    "render_heading_path",
]
```

This file will not import successfully until later tasks create the referenced
modules.

- [ ] **Step 3: Commit the shell only if it is part of a larger green commit**

Do not commit this task alone, because the package shell imports modules that do
not exist yet.

---

### Task 2: Move Draft Dataclasses and Heading Helpers

**Files:**
- Create: `src/lumberjack/core/splitters/drafts.py`
- Create: `src/lumberjack/core/splitters/headings.py`
- Modify: `src/lumberjack/core/splitter.py`
- Test: `tests/test_splitter.py`

- [ ] **Step 1: Create `drafts.py`**

Move these dataclasses from `src/lumberjack/core/splitter.py` into
`src/lumberjack/core/splitters/drafts.py`:

```python
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from lumberjack.core.models import HeadingPath, SectionNode


@dataclass(slots=True)
class _Entry:
    headings: HeadingPath
    body: str
    start_line: int | None
    end_line: int | None
    body_token_count: int = 0


@dataclass(slots=True)
class _ChunkDraft:
    entries: list[_Entry]
    headings: HeadingPath
    headings_token_count: int
    body_token_count: int
    token_count: int
    split_origin: Literal["section", "fragment", "text_piece", "merge"] = "section"
    chunk_type: str = "paragraph"


@dataclass(slots=True, frozen=True)
class _SectionTokenCounts:
    title: int
    body: int
    subtree: int


@dataclass(slots=True, frozen=True)
class _MeasuredSection:
    node: SectionNode
    counts: _SectionTokenCounts
    tail_text: str
    can_emit_as_single_chunk: bool
    children: tuple[_MeasuredSection, ...] = ()
```

- [ ] **Step 2: Create `headings.py`**

Move `render_heading_path()` and `common_heading_path()` into
`src/lumberjack/core/splitters/headings.py`:

```python
from __future__ import annotations

from collections.abc import Iterable

from lumberjack.core.models import HeadingPath
from lumberjack.core.utils import join_markdown


def render_heading_path(path: HeadingPath) -> str:
    def _render_heading(level: int, title: str) -> str:
        if level <= 0:
            return title.strip()
        return f"{'#' * level} {title.strip()}"

    return join_markdown([_render_heading(level, title) for level, title in path])


def common_heading_path(paths: Iterable[HeadingPath]) -> HeadingPath:
    iterator = iter(paths)
    first = tuple(next(iterator, ()))
    common = first
    for path in iterator:
        limit = min(len(common), len(path))
        index = 0
        while index < limit and common[index] == path[index]:
            index += 1
        common = common[:index]
        if not common:
            break
    return common
```

- [ ] **Step 3: Update temporary imports in old `splitter.py`**

In `src/lumberjack/core/splitter.py`, remove the moved definitions and import:

```python
from .splitters.drafts import (
    _ChunkDraft,
    _Entry,
    _MeasuredSection,
    _SectionTokenCounts,
)
from .splitters.headings import common_heading_path, render_heading_path
```

Also remove now-unused imports from `splitter.py`:

```python
from dataclasses import dataclass
from typing import Literal
```

Keep `TYPE_CHECKING` only if it is still needed.

- [ ] **Step 4: Run focused tests**

Run:

```bash
uv run pytest tests/test_splitter.py -q
```

Expected: same result as the baseline. Any new import or behavior failure must
be fixed before moving to Task 3.

---

### Task 3: Move Base Splitter and Concrete Strategies

**Files:**
- Create: `src/lumberjack/core/splitters/base.py`
- Create: `src/lumberjack/core/splitters/recursive.py`
- Create: `src/lumberjack/core/splitters/section.py`
- Create: `src/lumberjack/core/splitters/registry.py`
- Delete: `src/lumberjack/core/splitter.py`
- Test: `tests/test_splitter.py`

- [ ] **Step 1: Create `base.py`**

Move these items from the old `splitter.py` into
`src/lumberjack/core/splitters/base.py`:

```python
SEPARATOR = "\n\n"
SEPARATOR_DELTA_WINDOW_CHARS = 8
```

Move the complete existing `_BaseSplitter` class body, beginning at
`class _BaseSplitter(SplitterProtocol):` and ending immediately before
`class RecursiveSplitter(_BaseSplitter):`.

Use these imports at the top of `base.py`:

```python
from __future__ import annotations

from lumberjack.core.models import Chunk, DocumentAST, HeadingPath, MarkdownBlock, SectionNode, SplitOptions
from lumberjack.core.protocols import SplitterProtocol, TokenizerProtocol
from lumberjack.core.text_splitter import TextSplitter
from lumberjack.core.tokenizers import SimpleCharTokenizer
from lumberjack.core.utils import join_markdown
from lumberjack.core.splitters.drafts import _ChunkDraft, _Entry, _MeasuredSection, _SectionTokenCounts
from lumberjack.core.splitters.headings import common_heading_path, render_heading_path
```

Keep every method body byte-for-byte where practical. Do not change splitting or
token-estimate logic during this move.

- [ ] **Step 2: Create `recursive.py`**

Move `RecursiveSplitter` into `src/lumberjack/core/splitters/recursive.py` with
these imports:

```python
from __future__ import annotations

from lumberjack.core.splitters.base import _BaseSplitter
from lumberjack.core.splitters.drafts import _ChunkDraft, _Entry, _MeasuredSection
from lumberjack.core.splitters.headings import common_heading_path
```

Do not change method bodies.

- [ ] **Step 3: Create `section.py`**

Move `SectionSplitter` into `src/lumberjack/core/splitters/section.py` with
these imports:

```python
from __future__ import annotations

from lumberjack.core.splitters.base import _BaseSplitter
from lumberjack.core.splitters.drafts import _ChunkDraft, _MeasuredSection
```

Do not change method bodies.

- [ ] **Step 4: Create `registry.py`**

Move `SPLITTER_REGISTRY` and `create_splitter()` into
`src/lumberjack/core/splitters/registry.py`:

```python
from __future__ import annotations

from lumberjack.core.protocols import SplitterProtocol, TokenizerProtocol
from lumberjack.core.models import SplitOptions
from lumberjack.core.splitters.base import _BaseSplitter
from lumberjack.core.splitters.recursive import RecursiveSplitter
from lumberjack.core.splitters.section import SectionSplitter

SPLITTER_REGISTRY: dict[str, type[_BaseSplitter]] = {
    "default": RecursiveSplitter,
    "section": SectionSplitter,
    "recursive": RecursiveSplitter,
}


def create_splitter(
    name: str,
    tokenizer: TokenizerProtocol | None = None,
    options: SplitOptions | None = None,
) -> SplitterProtocol:
    normalized = name.strip().lower()
    cls = SPLITTER_REGISTRY.get(normalized)
    if cls is None:
        raise ValueError(f"Unsupported splitter: {name}")
    return cls(tokenizer=tokenizer, options=options)
```

- [ ] **Step 5: Delete the old module**

Delete `src/lumberjack/core/splitter.py` after all moved code exists in the new
package.

- [ ] **Step 6: Run focused tests to expose old imports**

Run:

```bash
uv run pytest tests/test_splitter.py -q
```

Expected before Task 4: this may fail with `ModuleNotFoundError` for
`lumberjack.core.splitter`. That is acceptable only if the failure is an import
path that Task 4 will migrate. Any syntax error or behavior assertion failure
must be fixed in this task.

---

### Task 4: Migrate Imports and Public Exports

**Files:**
- Modify: `src/lumberjack/core/__init__.py`
- Modify: `src/lumberjack/__init__.py` if it imports from old splitter paths
- Modify: `src/lumberjack/cli.py` if it imports from old splitter paths
- Modify: `src/lumberjack/web/routes.py` if it imports from old splitter paths
- Modify: `tests/test_splitter.py`
- Modify: `tests/test_api.py`
- Modify: `tests/test_docx_parser.py`
- Modify: `tests/test_html_parser.py`
- Modify: any other file found by `rg "core\\.splitter|from .*splitter import|import .*splitter"`

- [ ] **Step 1: Find old splitter imports**

Run:

```bash
rg -n "lumberjack\.core\.splitter|core\.splitter|from .*splitter import|import .*splitter" src tests README.md AGENTS.md docs
```

Expected: every old code import is listed for migration.

- [ ] **Step 2: Update `src/lumberjack/core/__init__.py`**

Replace:

```python
from .splitter import (
    RecursiveSplitter,
    SectionSplitter,
    create_splitter,
)
```

with:

```python
from .splitters import (
    RecursiveSplitter,
    SectionSplitter,
    create_splitter,
)
```

Keep the existing `__all__` names unchanged unless ruff reports an unused or
missing export.

- [ ] **Step 3: Update test imports**

In `tests/test_splitter.py`, replace:

```python
from lumberjack.core.splitter import (
    RecursiveSplitter,
    SectionSplitter,
    _ChunkDraft,
    _Entry,
    create_splitter,
)
```

with:

```python
from lumberjack.core.splitters import (
    RecursiveSplitter,
    SectionSplitter,
    create_splitter,
)
from lumberjack.core.splitters.drafts import _ChunkDraft, _Entry
```

In other tests, replace old concrete imports with:

```python
from lumberjack.core.splitters import RecursiveSplitter, create_splitter
```

or, for helper tests:

```python
from lumberjack.core.splitters.headings import common_heading_path, render_heading_path
```

- [ ] **Step 4: Update application imports**

For source files under `src/lumberjack/`, replace any old splitter imports with:

```python
from lumberjack.core.splitters import create_splitter
```

or relative equivalent:

```python
from .core.splitters import create_splitter
```

Use the style already present in that file.

- [ ] **Step 5: Ensure no old code imports remain**

Run:

```bash
rg -n "lumberjack\.core\.splitter|core\.splitter|src/lumberjack/core/splitter\.py" src tests
```

Expected: no matches.

- [ ] **Step 6: Run focused splitter and API import tests**

Run:

```bash
uv run pytest tests/test_splitter.py tests/test_api.py tests/test_docx_parser.py tests/test_html_parser.py -q
```

Expected: all selected tests pass, or failures match pre-existing baseline
issues recorded in Task 1.

---

### Task 5: Update Documentation

**Files:**
- Modify: `AGENTS.md`
- Modify: `README.md` if old splitter paths appear
- Modify: `docs/superpowers/specs/2026-06-18-splitter-organization-design.md` only if implementation differs from the approved design

- [ ] **Step 1: Find docs mentioning old splitter paths**

Run:

```bash
rg -n "core/splitter\.py|core\.splitter|splitter\.py|TextSplitter|RecursiveSplitter|SectionSplitter" AGENTS.md README.md docs
```

Expected: docs references to the old module path are visible.

- [ ] **Step 2: Update `AGENTS.md` architecture notes**

In `AGENTS.md`, describe the new package like this:

```markdown
### Splitters (`src/lumberjack/core/splitters/`)

- `base.py` — shared measuring, body splitting, draft merging, rendering, and finalization helpers
- `drafts.py` — internal draft and measured-section dataclasses
- `headings.py` — heading path rendering and common-prefix helpers
- `recursive.py` — `RecursiveSplitter`
- `section.py` — `SectionSplitter`
- `registry.py` — `SPLITTER_REGISTRY` and `create_splitter()`
- `__init__.py` — public splitter exports
```

Keep the existing `TextSplitter` note under shared/core utilities and clarify
that `src/lumberjack/core/text_splitter.py` handles oversized block fallback.

- [ ] **Step 3: Update README references if present**

If `README.md` mentions the old module path, replace it with:

```markdown
Document-level splitter strategies live in `src/lumberjack/core/splitters/`.
Oversized block fallback splitting lives in `src/lumberjack/core/text_splitter.py`.
```

If `README.md` only mentions splitter names or CLI options and not file paths,
do not edit it.

- [ ] **Step 4: Verify docs no longer point at deleted module**

Run:

```bash
rg -n "src/lumberjack/core/splitter\.py|lumberjack\.core\.splitter|core\.splitter" AGENTS.md README.md docs
```

Expected: no matches, except historical discussion in committed design/plan
files if those references explain the deleted module.

---

### Task 6: Format, Verify, and Commit

**Files:**
- All files changed by Tasks 1-5

- [ ] **Step 1: Run ruff auto-fix**

Run:

```bash
uv run ruff check --fix
```

Expected: exit 0. Review any automatic import sorting or unused-import changes.

- [ ] **Step 2: Run formatter**

Run:

```bash
uv run ruff format
```

Expected: exit 0.

- [ ] **Step 3: Run ruff clean check**

Run:

```bash
uv run ruff check
```

Expected: exit 0.

- [ ] **Step 4: Run focused splitter tests**

Run:

```bash
uv run pytest tests/test_splitter.py -q
```

Expected: exit 0.

- [ ] **Step 5: Run full Python test suite**

Run:

```bash
uv run pytest -q
```

Expected: exit 0, unless the pre-existing user deletion of
`tests/fixtures/markdown/deep-research-report.md` causes a known unrelated
failure. If so, report the exact failing test and do not restore the file unless
the user asks.

- [ ] **Step 6: Inspect final diff**

Run:

```bash
git diff -- src tests AGENTS.md README.md docs/superpowers/plans/2026-06-18-splitter-organization.md
```

Expected: structural splitter reorganization, import migrations, and docs
updates only. No chunk-splitting logic changes beyond moved code.

- [ ] **Step 7: Commit implementation**

Stage only files related to this refactor. Do not stage the pre-existing deleted
fixture unless the user explicitly says to include it.

Run:

```bash
git add src/lumberjack/core src/lumberjack/__init__.py src/lumberjack/cli.py src/lumberjack/web tests AGENTS.md README.md docs/superpowers/plans/2026-06-18-splitter-organization.md
git commit -m "refactor: split document splitters into package"
```

Expected: one commit containing the splitter package reorganization and docs
updates.

---

## Self-Review Checklist

- The approved spec says no compatibility layer should remain for
  `lumberjack.core.splitter`; Task 3 deletes the old module and Task 4 verifies
  old code imports are gone.
- The spec says `TextSplitter` should stay in `core/text_splitter.py`; no task
  moves it.
- The spec says splitter behavior must not change; Tasks 1, 4, and 6 use the
  existing splitter/API/parser tests as the behavior safety net.
- The spec says docs should be updated; Task 5 covers `AGENTS.md`, `README.md`,
  and docs grep verification.
- No task asks the worker to restore or stage the existing deleted fixture.
