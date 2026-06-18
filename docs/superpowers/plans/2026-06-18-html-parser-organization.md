# HTML Parser Organization Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Split the flat `src/lumberjack/core/html_parser.py` into an `html/` package that mirrors `markdown/` and `docx/`, while preserving behavior.

**Architecture:** Move code only — no logic changes. The document parser (`HTMLParser` + `_HTMLDocumentBuilder` + private helpers) goes into `html/parser.py`; the table-extraction utility (`HTMLTableParser` + `HTMLTable*` dataclasses) goes into `html/table_parser.py`. Migrate the three existing import sites, delete the old flat module, update docs.

**Tech Stack:** Python 3.13, stdlib `html.parser`, `dataclasses`, pytest, ruff.

**Spec:** `docs/superpowers/specs/2026-06-18-html-parser-organization-design.md`

**Baseline note:** This is a structural refactor. The existing tests are the safety net; there is no new behavior to TDD. Each task runs the existing tests and confirms they still pass.

---

## Source Map (reference — do not edit in place)

`src/lumberjack/core/html_parser.py` (846 lines) splits cleanly along these boundaries:

| Lines | Contents | Destination |
|-------|----------|-------------|
| 1–11  | Module docstring + imports | Split: each new file gets its own import subset |
| 13–31 | `_clean_text`, `_line_offsets`, `_attrs_dict` | `html/parser.py` |
| 32–70 | `_TextCollector`, `_ListItem`, `_ListCollector`, `_TableCollector` | `html/parser.py` |
| 72–416 | `_HTMLDocumentBuilder` | `html/parser.py` |
| 418–467 | `HTMLParser` | `html/parser.py` |
| 470–846 | `HTMLTableCell`, `HTMLTableRow`, `HTMLTable`, `HTMLTableParser` | `html/table_parser.py` |

The table section (470–846) uses only `re` and `dataclass` from the import block — not `field`, not the stdlib `HTMLParser`, not `Any`/`ClassVar`, not the `models` package.

---

## File Structure

- Create: `src/lumberjack/core/html/__init__.py`
  - Re-export `HTMLParser` only (mirror `docx/__init__.py`).
- Create: `src/lumberjack/core/html/parser.py`
  - `HTMLParser`, `_HTMLDocumentBuilder`, and the private helpers `_clean_text`, `_line_offsets`, `_attrs_dict`, `_TextCollector`, `_ListItem`, `_ListCollector`, `_TableCollector`.
- Create: `src/lumberjack/core/html/table_parser.py`
  - `HTMLTableParser`, `HTMLTable`, `HTMLTableRow`, `HTMLTableCell`.
- Delete: `src/lumberjack/core/html_parser.py`
  - After all imports are migrated.
- Modify: `src/lumberjack/core/markdown/parser.py` (line ~670)
  - `from ..html_parser import HTMLTableParser` → `from ..html.table_parser import HTMLTableParser`.
- Modify: `src/lumberjack/core/text_splitter.py` (line ~10)
  - `from .html_parser import HTMLTableParser, HTMLTableRow` → `from .html.table_parser import HTMLTableParser, HTMLTableRow`.
- Modify: `tests/test_html_parser.py` (lines ~5–8)
  - Split the single import into `lumberjack.core.html` and `lumberjack.core.html.table_parser`.
- Modify: `AGENTS.md`
  - Add `### HTML` architecture subsection.
- Modify: `README.md` / `README.zh-CN.md` only if they reference the old module path.

---

### Task 1: Establish Baseline

**Files:** none (verification only)

- [ ] **Step 1: Run focused HTML tests as the baseline**

Run:

```bash
uv run pytest tests/test_html_parser.py tests/test_html_table_integration.py -q
```

Expected: all pass. Record the count. If a pre-existing unrelated failure appears, record it; do not attempt to fix.

- [ ] **Step 2: Confirm the current import sites**

Run:

```bash
rg -n "html_parser" src tests
```

Expected matches (and only these):

```
src/lumberjack/core/markdown/parser.py:670:            from ..html_parser import HTMLTableParser
src/lumberjack/core/text_splitter.py:10:from .html_parser import HTMLTableParser, HTMLTableRow
tests/test_html_parser.py:5:from lumberjack.core.html_parser import (
```

No changes this task.

---

### Task 2: Create `html/parser.py` (document parser + helpers)

**Files:**
- Create: `src/lumberjack/core/html/parser.py`

- [ ] **Step 1: Create the file with the parser import block and module docstring**

Create `src/lumberjack/core/html/parser.py`. Top of file:

```python
"""HTML document parser producing the shared ``DocumentAST`` model."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from html.parser import HTMLParser as _StdlibHTMLParser
from typing import TYPE_CHECKING, Any, ClassVar

from ..models import DocumentAST, MarkdownBlock, MarkdownInline, SectionNode

if TYPE_CHECKING:
    pass
```

Note on imports vs. the old flat file:
- `re`, `dataclass`, `field`, `HTMLParser as _StdlibHTMLParser`, `Any`, `ClassVar`, and the `..models` line are carried over unchanged (the builder/parser body uses them).
- The import path for models changes from `from .models import` to `from ..models import` because the file now lives one level deeper.
- Do **not** include `TYPE_CHECKING`/`pass` lines unless needed; drop them if ruff later flags them as unused. The minimal correct block is the 8 lines above without the `if TYPE_CHECKING` block — start with:

```python
"""HTML document parser producing the shared ``DocumentAST`` model."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from html.parser import HTMLParser as _StdlibHTMLParser
from typing import Any, ClassVar

from ..models import DocumentAST, MarkdownBlock, MarkdownInline, SectionNode
```

- [ ] **Step 2: Append the parser section verbatim**

Copy lines 13–467 of the old `src/lumberjack/core/html_parser.py` (the private helpers `_clean_text`, `_line_offsets`, `_attrs_dict`, the `_TextCollector`/`_ListItem`/`_ListCollector`/`_TableCollector` dataclasses, `_HTMLDocumentBuilder`, and `HTMLParser`) **byte-for-byte** into `html/parser.py` immediately after the import block. Do not change any method body, signature, docstring, whitespace, or the `html.parser.HTMLParser as _StdlibHTMLParser` aliasing.

- [ ] **Step 3: Lint the new file**

Run:

```bash
uv run ruff check src/lumberjack/core/html/parser.py
```

Expected: clean. If ruff reports `field` (or any import) as unused, it means that symbol was only used by the table section — remove it from the import line. Do not change any code body to satisfy ruff; only adjust imports.

- [ ] **Step 4: Do not run tests yet**

The new file is not importable through the package until Task 4 creates `__init__.py` and migrates consumers. Committing now is fine because nothing references it yet.

- [ ] **Step 5: Commit**

```bash
git add src/lumberjack/core/html/parser.py
git commit -m "refactor(html): extract HTMLParser into html/parser.py"
```

---

### Task 3: Create `html/table_parser.py` (table utility + dataclasses)

**Files:**
- Create: `src/lumberjack/core/html/table_parser.py`

- [ ] **Step 1: Create the file with the table import block and module docstring**

Create `src/lumberjack/core/html/table_parser.py`. Top of file:

```python
"""HTML table extraction utility and parsed-table dataclasses."""

from __future__ import annotations

import re
from dataclasses import dataclass
```

This section uses only `re` and `dataclass` — not `field`, not the stdlib `HTMLParser`, not `Any`/`ClassVar`, not the `models` package.

- [ ] **Step 2: Append the table section verbatim**

Copy lines 470–846 of the old `src/lumberjack/core/html_parser.py` (`HTMLTableCell`, `HTMLTableRow`, `HTMLTable`, `HTMLTableParser`) **byte-for-byte** into `html/table_parser.py` immediately after the import block. Do not change any class definition, method body, regex pattern, or docstring.

- [ ] **Step 3: Lint the new file**

Run:

```bash
uv run ruff check src/lumberjack/core/html/table_parser.py
```

Expected: clean. If ruff reports `dataclass` as unused (it will not — every class in this section is decorated), investigate; otherwise do not change code bodies.

- [ ] **Step 4: Commit**

```bash
git add src/lumberjack/core/html/table_parser.py
git commit -m "refactor(html): extract HTMLTableParser into html/table_parser.py"
```

---

### Task 4: Create `html/__init__.py` and migrate consumers

**Files:**
- Create: `src/lumberjack/core/html/__init__.py`
- Modify: `src/lumberjack/core/markdown/parser.py` (line ~670)
- Modify: `src/lumberjack/core/text_splitter.py` (line ~10)
- Modify: `tests/test_html_parser.py` (lines ~5–8)

- [ ] **Step 1: Create the package export**

Create `src/lumberjack/core/html/__init__.py`:

```python
from .parser import HTMLParser

__all__ = ["HTMLParser"]
```

This mirrors `docx/__init__.py` (one document-parser re-export) and `markdown/__init__.py`. `HTMLTableParser` is intentionally **not** re-exported here — it is a block utility reached via `lumberjack.core.html.table_parser`.

- [ ] **Step 2: Migrate the Markdown parser import**

In `src/lumberjack/core/markdown/parser.py`, change (inside `_build_block`, around line 670):

```python
            from ..html_parser import HTMLTableParser
```

to:

```python
            from ..html.table_parser import HTMLTableParser
```

- [ ] **Step 3: Migrate the text_splitter import**

In `src/lumberjack/core/text_splitter.py`, change line 10:

```python
from .html_parser import HTMLTableParser, HTMLTableRow
```

to:

```python
from .html.table_parser import HTMLTableParser, HTMLTableRow
```

- [ ] **Step 4: Migrate the test import**

In `tests/test_html_parser.py`, replace lines 5–8:

```python
from lumberjack.core.html_parser import (
    HTMLParser,
    HTMLTableParser,
)
```

with:

```python
from lumberjack.core.html import HTMLParser
from lumberjack.core.html.table_parser import HTMLTableParser
```

- [ ] **Step 5: Verify no stale references remain**

Run:

```bash
rg -n "html_parser" src tests
```

Expected: no matches.

- [ ] **Step 6: Run focused tests**

Run:

```bash
uv run pytest tests/test_html_parser.py tests/test_html_table_integration.py -q
```

Expected: same pass count as Task 1's baseline.

- [ ] **Step 7: Commit**

```bash
git add src/lumberjack/core/html/__init__.py src/lumberjack/core/markdown/parser.py src/lumberjack/core/text_splitter.py tests/test_html_parser.py
git commit -m "refactor(html): migrate consumers to html/ package"
```

---

### Task 5: Delete the old flat module

**Files:**
- Delete: `src/lumberjack/core/html_parser.py`

- [ ] **Step 1: Confirm nothing imports it**

Run:

```bash
rg -n "html_parser" src tests
rg -n "core/html_parser|from \.html_parser|from \.\.html_parser" src tests
```

Expected: no matches.

- [ ] **Step 2: Delete the file**

Run:

```bash
git rm src/lumberjack/core/html_parser.py
```

- [ ] **Step 3: Run focused tests**

Run:

```bash
uv run pytest tests/test_html_parser.py tests/test_html_table_integration.py -q
```

Expected: same pass count as baseline.

- [ ] **Step 4: Commit**

```bash
git commit -m "refactor(html): remove flat html_parser.py module"
```

---

### Task 6: Update documentation

**Files:**
- Modify: `AGENTS.md`
- Modify: `README.md` / `README.zh-CN.md` only if they reference the old path

- [ ] **Step 1: Find docs that mention the old path**

Run:

```bash
rg -n "html_parser|HTMLParser|HTMLTableParser|core/html" AGENTS.md README.md README.zh-CN.md docs
```

Expected: matches in `AGENTS.md` architecture area (and possibly READMEs). Note every match.

- [ ] **Step 2: Add the HTML subsection to AGENTS.md**

In `AGENTS.md`, under the `### Markdown` / `### DOCX` sibling subsections inside `## Architecture`, add a parallel subsection. Place it after `### DOCX`:

```markdown
### HTML (`src/lumberjack/core/html/`)

- **Parser**: `src/lumberjack/core/html/parser.py`
  - `HTMLParser` — parses HTML into `DocumentAST`, mirroring `MarkdownItParser` and `DocxParser`
  - Built on stdlib `html.parser.HTMLParser` (aliased internally to avoid name shadowing)
  - Maps headings -> `SectionNode`, paragraphs -> `paragraph`, tables -> `html_table`, lists -> `list`, etc.
  - `_HTMLDocumentBuilder` is the event-driven internal builder
- **Table utility**: `src/lumberjack/core/html/table_parser.py`
  - `HTMLTableParser` + `HTMLTable`/`HTMLTableRow`/`HTMLTableCell`
  - Consumed by `markdown/parser.py` (to detect tables inside `html_block`) and `text_splitter.py` (to split oversized `html_table` blocks). Not used by `HTMLParser` itself.
```

Keep the existing `text_splitter.py` note under Shared — it still owns the oversized-block fallback; it merely imports `HTMLTableParser` from the new location.

- [ ] **Step 3: Update the Code Organization tree in AGENTS.md**

In the `## Code Organization` section, add the new package to the tree in alphabetical position (between `docx/` and `markdown/`):

```
        docx/
            __init__.py
            parser.py               # DocxParser
        html/
            __init__.py
            parser.py               # HTMLParser + _HTMLDocumentBuilder
            table_parser.py         # HTMLTableParser + HTMLTable*
        markdown/
```

If `html_parser.py` previously appeared as a flat entry under `core/` in the tree, remove it.

- [ ] **Step 4: Update READMEs if they reference the old path**

If `README.md` or `README.zh-CN.md` mention `core/html_parser.py` or `HTMLParser` module paths, replace with `src/lumberjack/core/html/`. If they only mention HTML support at the feature level (not file paths), do not edit them.

- [ ] **Step 5: Verify docs point only at the new path**

Run:

```bash
rg -n "core/html_parser|html_parser\.py" AGENTS.md README.md README.zh-CN.md
```

Expected: no matches.

- [ ] **Step 6: Commit**

```bash
git add AGENTS.md README.md README.zh-CN.md
git commit -m "docs: document html/ package layout"
```

---

### Task 7: Format, verify, and confirm

**Files:** all files changed by Tasks 2–6

- [ ] **Step 1: Run ruff auto-fix**

Run:

```bash
uv run ruff check --fix
```

Expected: exit 0. Review any import-sorting or unused-import changes in the new `html/` files only.

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

- [ ] **Step 4: Run focused HTML tests**

Run:

```bash
uv run pytest tests/test_html_parser.py tests/test_html_table_integration.py -q
```

Expected: same pass count as baseline.

- [ ] **Step 5: Run full Python suite**

Run:

```bash
uv run pytest -q
```

Expected: exit 0, unless the pre-existing deletion of `tests/fixtures/markdown/deep-research-report.md` causes a known unrelated failure. If so, report the exact failing test and do not restore the fixture.

- [ ] **Step 6: Inspect the final diff**

Run:

```bash
git diff master -- src tests AGENTS.md README.md README.zh-CN.md
```

Expected: structural HTML reorganization, import migrations, and docs updates only. No chunk-splitting, parsing, or token-estimate logic changes — only moved code and adjusted import paths.

- [ ] **Step 7: Commit any formatting changes**

If ruff changed any files in Steps 1–2:

```bash
git add -A
git commit -m "style: ruff format html package refactor"
```

If nothing changed, skip this step.

---

## Self-Review

**Spec coverage:**

- "Create `html/` package with `parser.py` + `table_parser.py` + `__init__.py`" → Tasks 2, 3, 4.
- "`__init__.py` re-exports only `HTMLParser`" → Task 4 Step 1.
- "Table utility goes into `html/table_parser.py`" → Task 3.
- "Migrate three import sites" → Task 4 Steps 2–4.
- "`test_html_table_integration.py` needs no import change" → acknowledged in Task 4 (only `test_html_parser.py` is edited); its coverage preserved via the focused test runs.
- "Delete old `html_parser.py` after migration" → Task 5.
- "Do not move `html_table` splitting out of `text_splitter.py`" → no task touches splitting logic.
- "Do not add HTML re-exports to `core/__init__.py`" → no task edits `core/__init__.py`.
- "Update AGENTS.md + READMEs" → Task 6.
- "Testing commands" → Tasks 1, 4, 5, 7.

**Placeholder scan:** No TBD/TODO. Every code step shows the exact import lines or the exact source-line range to move. ✓

**Type/name consistency:** `HTMLParser`, `HTMLTableParser`, `HTMLTable`, `HTMLTableRow`, `HTMLTableCell`, `_HTMLDocumentBuilder` — names used consistently across all tasks and match the spec. The `_StdlibHTMLParser` alias is preserved in `parser.py`. ✓

**Scope:** Single self-contained refactor producing working, fully-tested software. No decomposition needed. ✓
