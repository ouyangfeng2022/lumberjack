# Visitor Structured-Content Hooks Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add `visit_table_cell` / `visit_code_content` / `visit_math_content` hooks (and their `depart_*` pairs) so the visitor walks into table cells, code literals, and math expressions instead of leaving them as opaque block text.

**Architecture:** Dispatch point in `walk_block` (after children/inlines, before `depart_block`, outside the pruning gate) switches on `block.kind` and fires the appropriate hook pair. A private `_parse_table_rows` helper extracts cells from pipe-delimited markdown tables; `HTMLTableParser` handles HTML tables.

**Tech Stack:** Python 3.13+, pytest. Two files: `src/lumberjack/core/visitor.py` (dispatch + hooks + table helpers) and `tests/test_visitor.py` (6 new tests).

**Reference spec:** `docs/superpowers/specs/2026-06-18-visitor-structured-content-design.md`

---

## File Structure

- **Modify:** `src/lumberjack/core/visitor.py` — add structured-content dispatch in `walk_block`; add `_walk_table_cells`, `_walk_html_table_cells`, `_parse_table_rows`; add six new hook methods.
- **Modify:** `tests/test_visitor.py` — append six new tests.

No other files change.

---

## Task 1: Add structured-content dispatch + hooks + table helpers to visitor.py

**Files:**
- Modify: `src/lumberjack/core/visitor.py`

### Part A — Update `walk_block` to dispatch structured-content hooks

- [ ] **Step 1: Insert the structured-content dispatch block**

In `src/lumberjack/core/visitor.py`, find `walk_block`. It currently ends with:

```python
    def walk_block(self, block: MarkdownBlock) -> None:
        """Visit a block, its nested child blocks, then its inlines.

        Returning ``False`` from :meth:`visit_block` skips this block's
        nested child blocks and inlines; :meth:`depart_block` still fires.
        """
        descend = self.visit_block(block)
        if descend is not False:
            for child in block.children:
                self.walk_block(child)
            for inline in block.inlines:
                self.walk_inline(inline)
        self.depart_block(block)
```

Replace the closing `self.depart_block(block)` line with the dispatch block:

```python
    def walk_block(self, block: MarkdownBlock) -> None:
        """Visit a block, its nested child blocks, then its inlines.

        Returning ``False`` from :meth:`visit_block` skips this block's
        nested child blocks and inlines; :meth:`depart_block` still fires.
        """
        descend = self.visit_block(block)
        if descend is not False:
            for child in block.children:
                self.walk_block(child)
            for inline in block.inlines:
                self.walk_inline(inline)
        # --- structured-content dispatch (fires even when pruned) ---
        kind = block.kind
        if kind == "table" or kind == "html_table":
            self._walk_table_cells(block)
        elif kind == "code_fence":
            literal = block.attrs.get("literal", "")
            language = block.attrs.get("language", "")
            self.visit_code_content(literal, language)
            self.depart_code_content(literal, language)
        elif kind == "math_block":
            literal = block.attrs.get("literal", "")
            self.visit_math_content(literal)
            self.depart_math_content(literal)
        self.depart_block(block)
```

### Part B — Add table parsing helpers

- [ ] **Step 2: Add `_parse_table_rows` free function**

Add this free function between the `TYPE_CHECKING` block and the class definition (around line 7, after the imports):

```python


def _parse_table_rows(block_text: str) -> list[list[str]]:
    """Split pipe-delimited markdown table text into rows of cell strings.

    Returns:
        List of rows, each row a list of cell strings. The delimiter
        row (``|---|---|``) is excluded from the result.
    """
    lines = block_text.strip().split("\n")
    rows: list[list[str]] = []
    for line in lines:
        stripped = line.strip()
        if not stripped.startswith("|"):
            continue
        cells = [c.strip() for c in stripped.strip("|").split("|")]
        rows.append(cells)
    return rows
```

- [ ] **Step 3: Add `_walk_table_cells` method to the class**

In the "Hooks" section of the class, before the visitor hook methods, add:

```python
    # ------------------------------------------------------------------
    # Structured-content helpers (called by walk_block)
    # ------------------------------------------------------------------

    def _walk_table_cells(self, block: MarkdownBlock) -> None:
        """Walk table cells for markdown or HTML table blocks."""
        if block.kind == "html_table":
            self._walk_html_table_cells(block.text)
            return
        rows = _parse_table_rows(block.text)
        if len(rows) < 3:
            return  # no delimiter row — not a valid table
        # Row 0 = header, Row 1 = delimiter (skip), Rows 2+ = data
        for col_idx, cell_text in enumerate(rows[0]):
            self.visit_table_cell(0, col_idx, cell_text, is_header=True)
            self.depart_table_cell(0, col_idx, cell_text, is_header=True)
        for row_idx, row in enumerate(rows[2:], start=1):
            for col_idx, cell_text in enumerate(row):
                self.visit_table_cell(
                    row_idx, col_idx, cell_text, is_header=False
                )
                self.depart_table_cell(
                    row_idx, col_idx, cell_text, is_header=False
                )

    def _walk_html_table_cells(self, html_content: str) -> None:
        """Walk cells in an HTML table using :class:`~.html.table_parser.HTMLTableParser`."""
        from .html.table_parser import HTMLTableParser

        parser = HTMLTableParser()
        tables = parser.extract_tables(html_content)
        for table in tables:
            for header_row in table.headers:
                for col_idx, cell in enumerate(header_row.cells):
                    self.visit_table_cell(
                        0, col_idx, cell.text, is_header=True
                    )
                    self.depart_table_cell(
                        0, col_idx, cell.text, is_header=True
                    )
            for row_idx, row in enumerate(table.rows, start=1):
                for col_idx, cell in enumerate(row.cells):
                    self.visit_table_cell(
                        row_idx, col_idx, cell.text, is_header=False
                    )
                    self.depart_table_cell(
                        row_idx, col_idx, cell.text, is_header=False
                    )
```

### Part C — Add the six new hook methods

- [ ] **Step 4: Add structured-content hooks to the hooks section**

In the "Hooks — override in subclasses" section of the class, after the `depart_inline` hook and before `visit_document`, insert the six new hooks:

```python

    def visit_table_cell(
        self, row_idx: int, col_idx: int, text: str, is_header: bool
    ) -> None:
        """Hook called for each cell in a table or html_table block.

        Args:
            row_idx: 0-based row index (0 = header, 1+ = data rows).
            col_idx: 0-based column index within the row.
            text: Cell text content (markup stripped).
            is_header: Whether this cell belongs to the header row.
        """

    def depart_table_cell(
        self, row_idx: int, col_idx: int, text: str, is_header: bool
    ) -> None:
        """Hook called after a table cell has been visited."""

    def visit_code_content(self, literal: str, language: str) -> None:
        """Hook called for each code_fence block.

        Args:
            literal: Code text content (from ``attrs["literal"]``).
            language: Language tag (from ``attrs["language"]``), or ``""``.
        """

    def depart_code_content(self, literal: str, language: str) -> None:
        """Hook called after code content has been visited."""

    def visit_math_content(self, literal: str) -> None:
        """Hook called for each math_block block.

        Args:
            literal: Math expression text (from ``attrs["literal"]``).
        """

    def depart_math_content(self, literal: str) -> None:
        """Hook called after math content has been visited."""
```

### Verification

- [ ] **Step 5: Run the existing visitor suite to confirm no regressions**

Run: `uv run pytest tests/test_visitor.py -v`
Expected: 27 passed (new hooks are no-ops, so existing tests are unchanged).

- [ ] **Step 6: Lint and format**

Run: `uv run ruff check --fix src/lumberjack/core/visitor.py && uv run ruff format src/lumberjack/core/visitor.py`
Expected: no errors.

- [ ] **Step 7: Commit**

```bash
git add src/lumberjack/core/visitor.py
git commit -m "feat(visitor): add structured-content hooks for table/code/math"
```

---

## Task 2: Tests — code fence, math, and table cell hooks

**Files:**
- Modify: `tests/test_visitor.py` (append six new tests)

- [ ] **Step 1: Append all six tests at once (single script to avoid stale-guard issues)**

Run the following Python script:

```python
from pathlib import Path
p = Path("tests/test_visitor.py")
s = p.read_text()

addition = '''


def test_visitor_code_fence_hook() -> None:
    """visit_code_content receives literal and language from code_fence."""
    md = "# T\\n\\n```python\\nprint('hi')\\n```\\n"
    document = MarkdownParser().parse(md, document_title="code.md")

    class CodeCollector(MarkdownAstVisitor):
        def __init__(self) -> None:
            self.calls: list[tuple[str, str]] = []

        def visit_code_content(self, literal: str, language: str) -> None:
            self.calls.append((language, literal))

    collector = CodeCollector()
    collector.walk_document(document)

    assert collector.calls == [("python", "print('hi')")]


def test_visitor_math_block_hook() -> None:
    """visit_math_content receives literal from math_block."""
    md = "# T\\n\\n$$\\nx^2\\\\nx^3\\n$$\\n"
    document = MarkdownParser().parse(md, document_title="math.md")

    class MathCollector(MarkdownAstVisitor):
        def __init__(self) -> None:
            self.literals: list[str] = []

        def visit_math_content(self, literal: str) -> None:
            self.literals.append(literal)

    collector = MathCollector()
    collector.walk_document(document)

    assert collector.literals == ["x^2\\nx^3"]


def test_visitor_markdown_table_cell_hook() -> None:
    """visit_table_cell fires for each cell in a pipe-delimited table."""
    md = "# T\\n\\n| a | b |\\n|---|---|\\n| 1 | 2 |\\n"
    document = MarkdownParser().parse(md, document_title="table.md")

    class CellCollector(MarkdownAstVisitor):
        def __init__(self) -> None:
            self.cells: list[tuple[int, int, str, bool]] = []

        def visit_table_cell(
            self, row_idx: int, col_idx: int, text: str, is_header: bool
        ) -> None:
            self.cells.append((row_idx, col_idx, text, is_header))

    collector = CellCollector()
    collector.walk_document(document)

    # Header: row 0, cols 0 and 1
    # Data:   row 1, cols 0 and 1
    assert collector.cells == [
        (0, 0, "a", True),
        (0, 1, "b", True),
        (1, 0, "1", False),
        (1, 1, "2", False),
    ]


def test_visitor_html_table_cell_hook() -> None:
    """visit_table_cell fires for HTML table cells in an html_block."""
    md = (
        "# T\\n\\n"
        "<table>\\n"
        "<thead><tr><th>X</th><th>Y</th></tr></thead>\\n"
        "<tbody><tr><td>10</td><td>20</td></tr></tbody>\\n"
        "</table>\\n"
    )
    document = MarkdownParser().parse(md, document_title="html-table.md")

    class CellCollector(MarkdownAstVisitor):
        def __init__(self) -> None:
            self.cells: list[tuple[int, int, str, bool]] = []

        def visit_table_cell(
            self, row_idx: int, col_idx: int, text: str, is_header: bool
        ) -> None:
            self.cells.append((row_idx, col_idx, text, is_header))

    collector = CellCollector()
    collector.walk_document(document)

    assert ("X", True) in [(t, h) for _, _, t, h in collector.cells]
    assert ("10", False) in [(t, h) for _, _, t, h in collector.cells]
    assert len(collector.cells) >= 4  # header X,Y + data 10,20


def test_visitor_structured_content_combined() -> None:
    """All three structured-content hook groups fire in document order."""
    md = (
        "# T\\n\\n"
        "```\\ncode\\n```\\n\\n"
        "$$\\ne=mc^2\\n$$\\n\\n"
        "| h |\\n|---|\\n| v |\\n"
    )
    document = MarkdownParser().parse(md, document_title="combined.md")

    class CombinedCollector(MarkdownAstVisitor):
        def __init__(self) -> None:
            self.order: list[str] = []

        def visit_code_content(self, literal: str, language: str) -> None:
            self.order.append("code")

        def visit_math_content(self, literal: str) -> None:
            self.order.append("math")

        def visit_table_cell(
            self, row_idx: int, col_idx: int, text: str, is_header: bool
        ) -> None:
            if not self.order or self.order[-1] != "table":
                self.order.append("table")

    collector = CombinedCollector()
    collector.walk_document(document)

    # Fences, math, and table blocks appear in document order
    assert collector.order == ["code", "math", "table"]


def test_visitor_structured_hooks_are_noops_by_default() -> None:
    """Bare visitor walks a document with structured content without raising."""
    md = (
        "# T\\n\\n"
        "```\\ncode\\n```\\n\\n"
        "$$\\nx\\n$$\\n\\n"
        "| a |\\n|---|\\n| 1 |\\n"
    )
    document = MarkdownParser().parse(md, document_title="noop2.md")
    # No subclass overrides — should not raise
    MarkdownAstVisitor().walk_document(document)
'''

s = s.rstrip() + "\n" + addition
p.write_text(s)
print("appended 6 structured-content tests")
```

This script must be run with `uv run python <script>`.

- [ ] **Step 2: Run the new tests individually to verify they pass**

Run: `uv run pytest tests/test_visitor.py -v`
Expected: 33 passed (27 existing + 6 new).

- [ ] **Step 3: Lint and format**

Run: `uv run ruff check --fix tests/test_visitor.py && uv run ruff format tests/test_visitor.py`
Expected: no errors.

If any test assertion differs from the actual parser output (e.g., whitespace in code literal, different table cell structure), inspect the actual values with a quick `print()` and adjust the assertion. Do NOT change the visitor implementation.

- [ ] **Step 4: Commit**

```bash
git add tests/test_visitor.py
git commit -m "test(visitor): structured-content hooks for table/code/math"
```

---

## Task 3: Full-suite verification

**Files:** none modified.

- [ ] **Step 1: Run the complete test suite**

Run: `uv run pytest`
Expected: 207 passed (191 existing + 10 Spec A + 6 Spec B).

- [ ] **Step 2: Full lint sweep**

Run: `uv run ruff check src/ tests/`
Expected: All checks passed.

- [ ] **Step 3: If ruff made any changes in Step 2, commit them**

Run: `git status`
If clean: done. If modified:

```bash
git add -u
git commit -m "style: ruff format structured-content changes"
```

---

## Self-Review

**1. Spec coverage:**
- Structured-content dispatch in `walk_block` → Task 1, Step 1. ✓
- `_parse_table_rows` helper → Task 1, Step 2. ✓
- `_walk_table_cells` / `_walk_html_table_cells` → Task 1, Step 3. ✓
- Six new hook methods → Task 1, Step 4. ✓
- `depart_*` called for every `visit_*` → dispatch in Step 1 calls `depart_code_content` / `depart_math_content`; Step 3 calls `depart_table_cell` for each cell. ✓
- Test: code fence → Task 2, `test_visitor_code_fence_hook`. ✓
- Test: math block → Task 2, `test_visitor_math_block_hook`. ✓
- Test: markdown table cells → Task 2, `test_visitor_markdown_table_cell_hook`. ✓
- Test: HTML table cells → Task 2, `test_visitor_html_table_cell_hook`. ✓
- Test: combined order → Task 2, `test_visitor_structured_content_combined`. ✓
- Test: default no-op → Task 2, `test_visitor_structured_hooks_are_noops_by_default`. ✓
- Files touched: only `visitor.py` and `test_visitor.py`. ✓

**2. Placeholder scan:** No TBD/TODO. All test assertions are concrete. The conditional note in Task 2 Step 3 about adjusting assertions is a fallback, not a placeholder.

**3. Type consistency:**
- `visit_table_cell(self, row_idx: int, col_idx: int, text: str, is_header: bool)` used in Task 1 Step 3 (helper), Task 1 Step 4 (hook declaration), and all table tests. ✓
- `visit_code_content(self, literal: str, language: str)` consistent in dispatch and tests. ✓
- `visit_math_content(self, literal: str)` consistent. ✓
- Every `visit_*` has a matching `depart_*` with the same signature. ✓
