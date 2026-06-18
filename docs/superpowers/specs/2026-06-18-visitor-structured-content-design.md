# Visitor Structured-Content Hooks

**Date:** 2026-06-18
**Status:** Approved (design phase)
**Scope:** `src/lumberjack/core/visitor.py`, `src/lumberjack/core/html/table_parser.py`, `tests/test_visitor.py`

**Sequencing:** This is Spec B of two. Spec A (subtree pruning + `accept()` dispatch) is
a prerequisite and must be merged first.

## Problem

`MarkdownAstVisitor.walk_block` only recurses into `block.children` (nested
container blocks) and `block.inlines` (inline nodes). Structured block kinds —
tables, code fences, math blocks — carry their content in `block.attrs` and
`block.text`, which the visitor never traverses. A subclass that wants to
process table cells, code literals, or math expressions must bypass the
visitor and read `block.attrs` / `block.text` directly, defeating the purpose
of the visitor abstraction.

## Goal

Add three structured-content hook pairs that fire automatically inside
`walk_block` for recognized block kinds:

1. **Table cells** — `visit_table_cell` / `depart_table_cell` for each cell
   in `table` and `html_table` blocks (parsed lazily).
2. **Code content** — `visit_code_content` / `depart_code_content` for each
   `code_fence` block (provides literal + language).
3. **Math content** — `visit_math_content` / `depart_math_content` for each
   `math_block` block (provides literal).

All hooks are no-ops in the base class; subclasses override them to
participate.

`depart_*` is always called (paired with `visit_*`), even if the parsed
content is empty.

## Non-Goals

- Pruning structured-content hooks (returning `False` from `visit_table_cell`
  already does nothing — cells have no children).
- Changing the AST data model (`MarkdownBlock.text` / `attrs` stay as-is).
- Adding a `table_cell` block kind to the block registry (cells are not
  `MarkdownBlock` instances).
- Restructuring `text_splitter.py` to share the table-row parser; a private
  helper is added directly in `visitor.py` for now. Future refactoring can
  extract it if needed.

## Design

### Part 1 — Structured-content dispatch in `walk_block`

In `walk_block`, after the existing `children` + `inlines` loop but before
`depart_block`, add a kind-switch that fires the appropriate structured hook:

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
    # --- structured-content dispatch (always fires) ---
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

**Why the dispatch runs *after* children/inlines?** Table blocks have no
children or inlines; code fences and math blocks carry all their content in
`attrs`. Running the dispatch after the normal recursion keeps the ordering
consistent: a complete block (with all its substructure) is visited from top
to bottom. For future block kinds that might have both children *and*
structured content, the structured hooks fire last, after children, which
matches the "parent before children" mental model.

**Why the dispatch runs *outside* the `descend` gate?** Pruning
(`visit_block` returning `False`) skips `children` and `inlines`, but the
structured content is the block's *own* content, not its children. The user
intent of pruning is "don't recurse into my sub-blocks/inlines," not "don't
see this block's actual data." A visitor that prunes a `list` and expects to
also skip that list's structured content doesn't apply — `list` blocks have
no structured content. This is consistent: structured hooks are like inline
hooks for leaf blocks.

### Part 2 — Table cell parsing

A private helper `_parse_table_rows(text: str) -> list[list[str]]` in
`visitor.py` splits pipe-delimited markdown table text into rows and cells:

```python
def _parse_table_rows(block_text: str) -> list[list[str]]:
    """Split markdown table text into rows of cell strings."""
    lines = block_text.strip().split("\n")
    rows: list[list[str]] = []
    for line in lines:
        line = line.strip()
        if not line.startswith("|"):
            continue
        # Remove leading/trailing pipes, split on remaining pipes
        cells = [c.strip() for c in line.strip("|").split("|")]
        rows.append(cells)
    return rows
```

The `_walk_table_cells` method uses this for markdown `table` blocks and
`HTMLTableParser` for `html_table` blocks:

```python
def _walk_table_cells(self, block: MarkdownBlock) -> None:
    if block.kind == "html_table":
        self._walk_html_table_cells(block.text)
    else:
        rows = _parse_table_rows(block.text)
        if len(rows) >= 3:
            # Row 0 = header, Row 1 = delimiter (skip), Rows 2+ = data
            for col_idx, cell_text in enumerate(rows[0]):
                self.visit_table_cell(0, col_idx, cell_text, is_header=True)
                self.depart_table_cell(0, col_idx, cell_text, is_header=True)
            for row_idx, row in enumerate(rows[2:], start=1):
                for col_idx, cell_text in enumerate(row):
                    self.visit_table_cell(row_idx, col_idx, cell_text, is_header=False)
                    self.depart_table_cell(row_idx, col_idx, cell_text, is_header=False)
```

For `html_table` blocks, the HTML table parser is used:

```python
def _walk_html_table_cells(self, html_content: str) -> None:
    from .html.table_parser import HTMLTableParser

    parser = HTMLTableParser()
    tables = parser.extract_tables(html_content)
    for table in tables:
        for header_row in table.headers:
            for col_idx, cell in enumerate(header_row.cells):
                self.visit_table_cell(0, col_idx, cell.text, is_header=True)
                self.depart_table_cell(0, col_idx, cell.text, is_header=True)
        for row_idx, row in enumerate(table.rows, start=1):
            for col_idx, cell in enumerate(row.cells):
                self.visit_table_cell(
                    row_idx, col_idx, cell.text, is_header=False,
                )
                self.depart_table_cell(
                    row_idx, col_idx, cell.text, is_header=False,
                )
```

### Part 3 — New hook signatures

All new hooks are no-ops in the base class:

```python
def visit_table_cell(
    self, row_idx: int, col_idx: int, text: str, is_header: bool,
) -> None:
    """Hook called for each cell in a table or html_table block."""

def visit_code_content(self, literal: str, language: str) -> None:
    """Hook called for each code_fence block.

    Args:
        literal: Code text content (from ``attrs["literal"]``).
        language: Language tag (from ``attrs["language"]``), or ``""``.
    """

def visit_math_content(self, literal: str) -> None:
    """Hook called for each math_block block.

    Args:
        literal: Math expression text (from ``attrs["literal"]``).
    """

def depart_table_cell(
    self, row_idx: int, col_idx: int, text: str, is_header: bool,
) -> None:
    """Hook called after a table cell has been visited."""

def depart_code_content(self, literal: str, language: str) -> None:
    """Hook called after code content has been visited."""

def depart_math_content(self, literal: str) -> None:
    """Hook called after math content has been visited."""
```

The six hooks are placed in the "Hooks — override in subclasses" section,
after the existing hooks (before the final `depart_document`).

### Part 4 — Lazy import for `HTMLTableParser`

The `HTMLTableParser` import in `_walk_html_table_cells` is lazy (inside
the method body) to avoid a circular dependency between the `visitor` and
`html.table_parser` modules. The import path is `lumberjack.core.html.table_parser`.

## Test Plan

New tests appended to `tests/test_visitor.py`:

1. **Code fence hook** — a `CodeCollector(MarkdownAstVisitor)` overrides
   `visit_code_content(literal, language)` and captures `(language, literal)`.
   Parse a document with a `code_fence` block and assert the captured tuple
   matches.

2. **Math block hook** — a `MathCollector` overrides `visit_math_content`
   and captures the literal. Parse a document with `$$...$$` and assert.

3. **Markdown table cell hook** — a `CellCollector` overrides
   `visit_table_cell` and captures `(row_idx, col_idx, text, is_header)`.
   Parse a 2-row table and assert the collected cells match the expected
   header + data rows.

4. **HTML table cell hook** — same `CellCollector` on an `html_table` block
   (parse a markdown document that includes an HTML `<table>`). Assert cells
   are collected.

5. **Combined structured content walk** — a single visitor overrides all
   three hook groups on a document with a table, a code fence, and a math
   block. Assert all hooks fire in the expected order (block-level hooks
   fire within each `walk_block` call in document order).

6. **Default no-op hooks** — bare `MarkdownAstVisitor().walk_document(doc)`
   on a document with tables/code/math does not raise (regression).

Existing 27 tests continue to pass.

## Files Touched

- `src/lumberjack/core/visitor.py` — add structured-content dispatch in
  `walk_block`; add `_walk_table_cells`, `_walk_html_table_cells`,
  `_parse_table_rows`; add six new hook methods.
- `tests/test_visitor.py` — append six new tests.

No changes to `models.py`, `__init__.py`, parsers, splitters, CLI, web, or
`text_splitter.py`.

## Risks

- **Performance**: `_parse_table_rows` and `HTMLTableParser.extract_tables`
  run on every `walk_block` call for table/html_table blocks. Both are
  O(cells) and cheap; acceptable for the visitor's typical use case
  (single-pass analysis).
- **HTML table cell indexing**: Header rows now use `enumerate(header_row.cells)`
  for accurate `col_idx`, matching the markdown table path.
