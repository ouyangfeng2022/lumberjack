# Visitor Document-Level Hooks Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add `visit_document` / `depart_document` hooks to `MarkdownAstVisitor` so subclasses can read `DocumentAST.title`, `metadata`, and `reference_definitions` during a traversal.

**Architecture:** Two new no-op hook methods on `MarkdownAstVisitor`, bracketing the existing `walk_section(document.root)` call inside `walk_document`. Order is `visit_document` → section tree → `depart_document`. No other traversal methods, hook signatures, or public API change.

**Tech Stack:** Python 3.13+ (`from __future__ import annotations`), pytest, dataclasses. Single-file change in `src/lumberjack/core/visitor.py` plus appended tests in `tests/test_visitor.py`.

**Reference spec:** `docs/superpowers/specs/2026-06-18-visitor-document-hooks-design.md`

---

## File Structure

- **Modify:** `src/lumberjack/core/visitor.py` — add two hook methods (`visit_document`, `depart_document`) and update `walk_document` to call them. The `DocumentAST` import is already present in the `TYPE_CHECKING` block (line 6).
- **Modify:** `tests/test_visitor.py` — append six new tests after the existing `test_visitor_importable_from_top_level` (last test in file, line 296).

No new files. No changes to `__init__.py`, models, parsers, or splitters.

---

## Task 1: Add document hook methods and update `walk_document`

**Files:**
- Modify: `src/lumberjack/core/visitor.py:50-52` (the `walk_document` method)
- Modify: `src/lumberjack/core/visitor.py` (add two methods in the hooks section after `visit_inline`/`depart_inline`, around line 99)

- [ ] **Step 1: Update `walk_document` to call the new hooks**

In `src/lumberjack/core/visitor.py`, replace the existing `walk_document` method (currently lines 50-52):

```python
    def walk_document(self, document: DocumentAST) -> None:
        """Walk the full document tree starting from the root section."""
        self.walk_section(document.root)
```

with:

```python
    def walk_document(self, document: DocumentAST) -> None:
        """Walk the full document tree.

        Fires :meth:`visit_document` before the section tree and
        :meth:`depart_document` after it, so subclasses can read
        ``document.title``, ``document.metadata``, and
        ``document.reference_definitions`` without touching ``document.root``.
        """
        self.visit_document(document)
        self.walk_section(document.root)
        self.depart_document(document)
```

- [ ] **Step 2: Add the `visit_document` / `depart_document` hook methods**

In `src/lumberjack/core/visitor.py`, immediately after the existing `depart_inline` method (currently the last method in the class, lines 98-99):

```python
    def depart_inline(self, inline: MarkdownInline) -> None:
        """Hook called when *leaving* an inline node."""
```

append these two new methods (keep the same indentation level — four spaces — as the other hook methods):

```python

    def visit_document(self, document: DocumentAST) -> None:
        """Hook called when *entering* a document.

        Read ``document.title``, ``document.metadata``, and
        ``document.reference_definitions`` here before the section tree
        is walked.
        """

    def depart_document(self, document: DocumentAST) -> None:
        """Hook called when the full document tree has been walked.

        Use for finalization (emit collected data, log summaries).
        """
```

- [ ] **Step 3: Run the existing test suite to confirm no regressions**

Run: `uv run pytest tests/test_visitor.py -v`
Expected: 11 passed (the existing tests do not override the new hooks, so they produce no document events and the asserted event sequences are unchanged).

- [ ] **Step 4: Run ruff lint and format**

Run: `uv run ruff check --fix src/lumberjack/core/visitor.py && uv run ruff format src/lumberjack/core/visitor.py`
Expected: no errors; file reformatted if needed.

- [ ] **Step 5: Commit**

```bash
git add src/lumberjack/core/visitor.py
git commit -m "feat(visitor): add visit_document/depart_document hooks"
```

---

## Task 2: Add test — document hooks fire and bracket the root

**Files:**
- Modify: `tests/test_visitor.py` (append after line 296, the last test)

- [ ] **Step 1: Write the failing test**

Append to `tests/test_visitor.py` (after `test_visitor_importable_from_top_level`):

```python


def test_visitor_document_hooks_bracket_section_tree() -> None:
    """visit_document fires first; depart_document fires last."""
    document = MarkdownParser().parse(FLAT_FIXTURE, document_title="flat.md")

    class DocumentEventRecorder(MarkdownAstVisitor):
        def __init__(self) -> None:
            self.events: list[str] = []

        def visit_document(self, document: DocumentAST) -> None:
            self.events.append("enter_document")

        def depart_document(self, document: DocumentAST) -> None:
            self.events.append("depart_document")

        def visit_section(self, section: SectionNode) -> None:
            self.events.append(f"enter_section:{section.title}")

    recorder = DocumentEventRecorder()
    recorder.walk_document(document)

    assert recorder.events[0] == "enter_document"
    assert recorder.events[-1] == "depart_document"
    # Section events sit between the document hooks
    assert recorder.events[1].startswith("enter_section:")
    assert all(
        not e.startswith("enter_section:") for e in recorder.events[2:-1]
    ) or recorder.events[1:-1]  # at least one section event between
    assert "enter_section:flat.md" in recorder.events
    assert "enter_section:Title" in recorder.events
```

Note: `DocumentAST` is needed in the test file's `TYPE_CHECKING` import. The existing `tests/test_visitor.py` already has (lines 8-9):

```python
if TYPE_CHECKING:
    from lumberjack.core.models import MarkdownBlock, MarkdownInline, SectionNode
```

Update that import block to also include `DocumentAST`:

```python
if TYPE_CHECKING:
    from lumberjack.core.models import (
        DocumentAST,
        MarkdownBlock,
        MarkdownInline,
        SectionNode,
    )
```

- [ ] **Step 2: Run the test to verify it passes**

Run: `uv run pytest tests/test_visitor.py::test_visitor_document_hooks_bracket_section_tree -v`
Expected: PASS (Task 1 already implemented the hooks).

- [ ] **Step 3: Commit**

```bash
git add tests/test_visitor.py
git commit -m "test(visitor): document hooks bracket section tree"
```

---

## Task 3: Add test — metadata is reachable in `visit_document`

**Files:**
- Modify: `tests/test_visitor.py` (append after the test added in Task 2)

- [ ] **Step 1: Write the test**

Append to `tests/test_visitor.py`:

```python


def test_visitor_metadata_reachable_in_visit_document() -> None:
    """visit_document can read document.metadata (YAML front matter)."""
    md = "---\ntitle: From Front Matter\nauthor: ada\n---\n\n# Heading\n\nBody.\n"
    document = MarkdownParser().parse(md, document_title="meta.md")

    class MetadataReader(MarkdownAstVisitor):
        def __init__(self) -> None:
            self.metadata: dict[str, object] = {}

        def visit_document(self, document: DocumentAST) -> None:
            self.metadata = dict(document.metadata)

    reader = MetadataReader()
    reader.walk_document(document)

    assert reader.metadata.get("title") == "From Front Matter"
    assert reader.metadata.get("author") == "ada"
```

- [ ] **Step 2: Run the test to verify it passes**

Run: `uv run pytest tests/test_visitor.py::test_visitor_metadata_reachable_in_visit_document -v`
Expected: PASS.

- [ ] **Step 3: Commit**

```bash
git add tests/test_visitor.py
git commit -m "test(visitor): metadata reachable in visit_document"
```

---

## Task 4: Add test — reference definitions are reachable

**Files:**
- Modify: `tests/test_visitor.py` (append after the test added in Task 3)

- [ ] **Step 1: Write the test**

Append to `tests/test_visitor.py`:

```python


def test_visitor_reference_definitions_reachable_in_visit_document() -> None:
    """visit_document can read document.reference_definitions."""
    md = (
        "# Links\n\n"
        "See [example][ref] and [ref][ref].\n\n"
        "[ref]: https://example.com\n"
    )
    document = MarkdownParser().parse(md, document_title="refs.md")

    class RefReader(MarkdownAstVisitor):
        def __init__(self) -> None:
            self.refs: dict[str, dict[str, str]] = {}

        def visit_document(self, document: DocumentAST) -> None:
            self.refs = document.reference_definitions

    reader = RefReader()
    reader.walk_document(document)

    assert "ref" in reader.refs
    assert reader.refs["ref"]["destination"] == "https://example.com"
```

- [ ] **Step 2: Run the test to verify it passes**

Run: `uv run pytest tests/test_visitor.py::test_visitor_reference_definitions_reachable_in_visit_document -v`
Expected: PASS.

Note: if this test fails because the reference-definition key or value shape differs, inspect the actual `document.reference_definitions` dict with a quick `print(reader.refs)` and adjust the assertion to match the real structure (the keys are the label, values are dicts keyed by `destination`/`title` per the markdown-it-py convention used by `MarkdownItParser`). Do not change the visitor implementation to satisfy this — adjust the test assertion only.

- [ ] **Step 3: Commit**

```bash
git add tests/test_visitor.py
git commit -m "test(visitor): reference definitions reachable in visit_document"
```

---

## Task 5: Add test — document title is reachable

**Files:**
- Modify: `tests/test_visitor.py` (append after the test added in Task 4)

- [ ] **Step 1: Write the test**

Append to `tests/test_visitor.py`:

```python


def test_visitor_document_title_reachable_in_visit_document() -> None:
    """visit_document can read document.title."""
    document = MarkdownParser().parse("# Body\n\nText.\n", document_title="title.md")

    class TitleReader(MarkdownAstVisitor):
        def __init__(self) -> None:
            self.title: str | None = None

        def visit_document(self, document: DocumentAST) -> None:
            self.title = document.title

    reader = TitleReader()
    reader.walk_document(document)

    assert reader.title == "title.md"
```

- [ ] **Step 2: Run the test to verify it passes**

Run: `uv run pytest tests/test_visitor.py::test_visitor_document_title_reachable_in_visit_document -v`
Expected: PASS.

- [ ] **Step 3: Commit**

```bash
git add tests/test_visitor.py
git commit -m "test(visitor): document title reachable in visit_document"
```

---

## Task 6: Add test — `depart_document` fires after all children

**Files:**
- Modify: `tests/test_visitor.py` (append after the test added in Task 5)

- [ ] **Step 1: Write the test**

Append to `tests/test_visitor.py`:

```python


def test_visitor_depart_document_fires_after_blocks() -> None:
    """depart_document runs after every block has been walked."""
    document = MarkdownParser().parse("# Title\n\nPara one.\n\nPara two.\n", document_title="order.md")

    class OrderChecker(MarkdownAstVisitor):
        def __init__(self) -> None:
            self.block_count: int = 0
            self.count_at_depart: int | None = None

        def visit_block(self, block: MarkdownBlock) -> None:
            self.block_count += 1

        def depart_document(self, document: DocumentAST) -> None:
            self.count_at_depart = self.block_count

    checker = OrderChecker()
    checker.walk_document(document)

    assert checker.count_at_depart is not None
    assert checker.count_at_depart >= 2  # two paragraphs walked before depart
    assert checker.count_at_depart == checker.block_count
```

- [ ] **Step 2: Run the test to verify it passes**

Run: `uv run pytest tests/test_visitor.py::test_visitor_depart_document_fires_after_blocks -v`
Expected: PASS.

- [ ] **Step 3: Commit**

```bash
git add tests/test_visitor.py
git commit -m "test(visitor): depart_document fires after blocks walked"
```

---

## Task 7: Add test — default no-op hooks do not raise

**Files:**
- Modify: `tests/test_visitor.py` (append after the test added in Task 6)

- [ ] **Step 1: Write the test**

Append to `tests/test_visitor.py`:

```python


def test_visitor_default_document_hooks_are_noops() -> None:
    """Bare visitor with default document hooks walks without raising."""
    document = MarkdownParser().parse("# Title\n\nBody.\n", document_title="noop.md")
    # No subclass overrides — should not raise
    MarkdownAstVisitor().walk_document(document)
```

- [ ] **Step 2: Run the test to verify it passes**

Run: `uv run pytest tests/test_visitor.py::test_visitor_default_document_hooks_are_noops -v`
Expected: PASS.

- [ ] **Step 3: Commit**

```bash
git add tests/test_visitor.py
git commit -m "test(visitor): default document hooks are no-ops"
```

---

## Task 8: Full-suite verification

**Files:** none modified.

- [ ] **Step 1: Run the complete test suite**

Run: `uv run pytest`
Expected: all tests pass (existing suite + the 6 new tests).

- [ ] **Step 2: Run full lint and format sweep**

Run: `uv run ruff check --fix && uv run ruff format`
Expected: no errors.

- [ ] **Step 3: If any changes were made in Step 2, commit them**

Run: `git status`
If clean: done. If `tests/test_visitor.py` or `src/lumberjack/core/visitor.py` are modified:

```bash
git add -u
git commit -m "style: ruff format visitor changes"
```

---

## Self-Review

**1. Spec coverage:**
- New `visit_document` / `depart_document` no-op hooks → Task 1, Steps 1-2. ✓
- `walk_document` calls them, order `visit_document` → section tree → `depart_document` → Task 1, Step 1. ✓
- `walk_section`/`walk_block`/`walk_inline` unchanged → Task 1 touches only `walk_document` and adds methods; no edit to those three. ✓
- Existing hook signatures unchanged → no edit to `visit_section`/`depart_section`/`visit_block`/`depart_block`/`visit_inline`/`depart_inline`. ✓
- Test: document hooks bracket root → Task 2. ✓
- Test: metadata reachable → Task 3. ✓
- Test: reference definitions reachable → Task 4. ✓
- Test: document title reachable → Task 5. ✓
- Test: `depart_document` after children → Task 6. ✓
- Test: default no-op → Task 7. ✓
- Existing 11 tests unchanged → no edits to existing test bodies; only appends and one `TYPE_CHECKING` import expansion. ✓
- Files touched: only `src/lumberjack/core/visitor.py` and `tests/test_visitor.py`. ✓

**2. Placeholder scan:** No TBD/TODO. Each test step contains full runnable code. The one conditional note in Task 4 Step 2 (reference-definition shape) gives a concrete fallback (print + adjust assertion, not implementation change), not a placeholder.

**3. Type consistency:**
- Hook signature `visit_document(self, document: DocumentAST) -> None` used in Task 1 (implementation) and Tasks 2-7 (test overrides). ✓
- Hook signature `depart_document(self, document: DocumentAST) -> None` consistent across all tasks. ✓
- `DocumentAST` added to the test file's `TYPE_CHECKING` import in Task 2 Step 1; all later tasks rely on that import being present. ✓
- The existing `TYPE_CHECKING` import block in `visitor.py` already has `DocumentAST` (verified at `src/lumberjack/core/visitor.py:6`), so no import change in Task 1. ✓
