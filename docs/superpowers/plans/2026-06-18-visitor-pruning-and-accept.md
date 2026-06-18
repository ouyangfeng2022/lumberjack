# Visitor Pruning + accept() Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add subtree-pruning (any `visit_*` returning `False` skips that node's children) and `accept(visitor)` dispatch on AST nodes, while keeping all existing visitor behavior backward-compatible.

**Architecture:** Two coordinated changes — (1) the four `walk_*` methods in `MarkdownAstVisitor` gate recursion on the `visit_*` return value; (2) each AST node class in `models.py` gains an `accept(visitor)` method that calls the matching `walk_*`. The `MarkdownAstVisitor` import in `models.py` is `TYPE_CHECKING`-only to avoid a cycle.

**Tech Stack:** Python 3.13+ (`from __future__ import annotations`), pytest, dataclasses. Two source files (`src/lumberjack/core/visitor.py`, `src/lumberjack/core/models.py`) plus test appends in `tests/test_visitor.py`.

**Reference spec:** `docs/superpowers/specs/2026-06-18-visitor-pruning-and-accept-design.md`

---

## File Structure

- **Modify:** `src/lumberjack/core/visitor.py` — gate recursion in `walk_document`, `walk_section`, `walk_block`, `walk_inline`; update `visit_document`/`visit_section`/`visit_block`/`visit_inline` return annotations to `bool | None` and add the pruning docstring note.
- **Modify:** `src/lumberjack/core/models.py` — add `MarkdownAstVisitor` to the `TYPE_CHECKING` import block; add `accept(visitor)` method to `DocumentAST`, `SectionNode`, `MarkdownBlock`, `MarkdownInline`.
- **Modify:** `tests/test_visitor.py` — append 10 new tests (pruning + backward-compat + accept dispatch + combined).

No new files. No changes to `__init__.py`, parsers, splitters, CLI, or web.

---

## Task 1: Add pruning to the four `walk_*` methods + update `visit_*` annotations

**Files:**
- Modify: `src/lumberjack/core/visitor.py` (the four `walk_*` methods and the four `visit_*` hooks)

- [ ] **Step 1: Update `walk_document` to gate on `visit_document`'s return value**

In `src/lumberjack/core/visitor.py`, replace the current `walk_document` method:

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

with:

```python
    def walk_document(self, document: DocumentAST) -> None:
        """Walk the full document tree.

        Fires :meth:`visit_document` before the section tree and
        :meth:`depart_document` after it, so subclasses can read
        ``document.title``, ``document.metadata``, and
        ``document.reference_definitions`` without touching ``document.root``.

        Returning ``False`` from :meth:`visit_document` skips the section tree;
        :meth:`depart_document` still fires.
        """
        descend = self.visit_document(document)
        if descend is not False:
            self.walk_section(document.root)
        self.depart_document(document)
```

- [ ] **Step 2: Update `walk_section` to gate on `visit_section`'s return value**

Replace the current `walk_section`:

```python
    def walk_section(self, section: SectionNode) -> None:
        """Recursively visit a section's blocks and child sections."""
        self.visit_section(section)
        for block in section.blocks:
            self.walk_block(block)
        for child in section.children:
            self.walk_section(child)
        self.depart_section(section)
```

with:

```python
    def walk_section(self, section: SectionNode) -> None:
        """Recursively visit a section's blocks and child sections.

        Returning ``False`` from :meth:`visit_section` skips this section's
        blocks and child sections; :meth:`depart_section` still fires.
        """
        descend = self.visit_section(section)
        if descend is not False:
            for block in section.blocks:
                self.walk_block(block)
            for child in section.children:
                self.walk_section(child)
        self.depart_section(section)
```

- [ ] **Step 3: Update `walk_block` to gate on `visit_block`'s return value**

Replace the current `walk_block`:

```python
    def walk_block(self, block: MarkdownBlock) -> None:
        """Visit a block, its nested child blocks, then its inlines."""
        self.visit_block(block)
        for child in block.children:
            self.walk_block(child)
        for inline in block.inlines:
            self.walk_inline(inline)
        self.depart_block(block)
```

with:

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

- [ ] **Step 4: Update `walk_inline` to gate on `visit_inline`'s return value**

Replace the current `walk_inline`:

```python
    def walk_inline(self, inline: MarkdownInline) -> None:
        """Visit an inline node and its nested children."""
        self.visit_inline(inline)
        for child in inline.children:
            self.walk_inline(child)
        self.depart_inline(inline)
```

with:

```python
    def walk_inline(self, inline: MarkdownInline) -> None:
        """Visit an inline node and its nested children.

        Returning ``False`` from :meth:`visit_inline` skips this inline's
        nested children; :meth:`depart_inline` still fires.
        """
        descend = self.visit_inline(inline)
        if descend is not False:
            for child in inline.children:
                self.walk_inline(child)
        self.depart_inline(inline)
```

- [ ] **Step 5: Update the four `visit_*` hook annotations to `-> bool | None`**

In the "Hooks — override in subclasses" section of `src/lumberjack/core/visitor.py`, update the four `visit_*` hooks. Replace:

```python
    def visit_section(self, section: SectionNode) -> None:
        """Hook called when *entering* a section node."""

    def depart_section(self, section: SectionNode) -> None:
        """Hook called when *leaving* a section node."""

    def visit_block(self, block: MarkdownBlock) -> None:
        """Hook called when *entering* a block node."""

    def depart_block(self, block: MarkdownBlock) -> None:
        """Hook called when *leaving* a block node."""

    def visit_inline(self, inline: MarkdownInline) -> None:
        """Hook called when *entering* an inline node."""

    def depart_inline(self, inline: MarkdownInline) -> None:
        """Hook called when *leaving* an inline node."""

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

with:

```python
    def visit_section(self, section: SectionNode) -> bool | None:
        """Hook called when *entering* a section node.

        Return ``False`` to skip this section's blocks and child sections.
        :meth:`depart_section` still fires.
        """

    def depart_section(self, section: SectionNode) -> None:
        """Hook called when *leaving* a section node."""

    def visit_block(self, block: MarkdownBlock) -> bool | None:
        """Hook called when *entering* a block node.

        Return ``False`` to skip this block's nested child blocks and
        inlines. :meth:`depart_block` still fires.
        """

    def depart_block(self, block: MarkdownBlock) -> None:
        """Hook called when *leaving* a block node."""

    def visit_inline(self, inline: MarkdownInline) -> bool | None:
        """Hook called when *entering* an inline node.

        Return ``False`` to skip this inline's nested children.
        :meth:`depart_inline` still fires.
        """

    def depart_inline(self, inline: MarkdownInline) -> None:
        """Hook called when *leaving* an inline node."""

    def visit_document(self, document: DocumentAST) -> bool | None:
        """Hook called when *entering* a document.

        Read ``document.title``, ``document.metadata``, and
        ``document.reference_definitions`` here before the section tree
        is walked.

        Return ``False`` to skip the entire section tree.
        :meth:`depart_document` still fires.
        """

    def depart_document(self, document: DocumentAST) -> None:
        """Hook called when the full document tree has been walked.

        Use for finalization (emit collected data, log summaries).
        """
```

- [ ] **Step 6: Run the existing visitor test suite to confirm no regressions**

Run: `uv run pytest tests/test_visitor.py -v`
Expected: 17 passed (existing hooks all return `None`, so `descend is not False` is always true and traversal is unchanged).

- [ ] **Step 7: Run ruff lint and format**

Run: `uv run ruff check --fix src/lumberjack/core/visitor.py && uv run ruff format src/lumberjack/core/visitor.py`
Expected: no errors.

- [ ] **Step 8: Commit**

```bash
git add src/lumberjack/core/visitor.py
git commit -m "feat(visitor): support subtree pruning via visit_* return value"
```

---

## Task 2: Add `accept(visitor)` to the AST node classes

**Files:**
- Modify: `src/lumberjack/core/models.py` (add `TYPE_CHECKING` import; add `accept` to 4 classes)

- [ ] **Step 1: Add `MarkdownAstVisitor` to the `TYPE_CHECKING` import block**

At the top of `src/lumberjack/core/models.py`, find the existing imports:

```python
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any
```

Replace with (add a `TYPE_CHECKING` import block):

```python
from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from .visitor import MarkdownAstVisitor
```

- [ ] **Step 2: Add `accept` to `MarkdownInline`**

In `src/lumberjack/core/models.py`, find `MarkdownInline`. It currently ends:

```python
    kind: str
    text: str = ""
    children: tuple[MarkdownInline, ...] = ()
    attrs: dict[str, Any] = field(default_factory=dict)
```

Replace with (append the method):

```python
    kind: str
    text: str = ""
    children: tuple[MarkdownInline, ...] = ()
    attrs: dict[str, Any] = field(default_factory=dict)

    def accept(self, visitor: MarkdownAstVisitor) -> None:
        """Dispatch this inline to ``visitor.walk_inline``."""
        visitor.walk_inline(self)
```

- [ ] **Step 3: Add `accept` to `MarkdownBlock`**

In `src/lumberjack/core/models.py`, find `MarkdownBlock`. It currently ends:

```python
    kind: str
    text: str
    start_line: int | None = None
    end_line: int | None = None
    children: tuple[MarkdownBlock, ...] = ()
    inlines: tuple[MarkdownInline, ...] = ()
    attrs: dict[str, Any] = field(default_factory=dict)
```

Replace with (append the method):

```python
    kind: str
    text: str
    start_line: int | None = None
    end_line: int | None = None
    children: tuple[MarkdownBlock, ...] = ()
    inlines: tuple[MarkdownInline, ...] = ()
    attrs: dict[str, Any] = field(default_factory=dict)

    def accept(self, visitor: MarkdownAstVisitor) -> None:
        """Dispatch this block to ``visitor.walk_block``."""
        visitor.walk_block(self)
```

- [ ] **Step 4: Add `accept` to `SectionNode`**

In `src/lumberjack/core/models.py`, find `SectionNode`. It currently has these methods at the end:

```python
    def add_block(self, block: MarkdownBlock) -> None:
        """Append a block (roughly one paragraph) to this section."""
        self.blocks.append(block)

    def add_child(self, child: SectionNode) -> None:
        self.children.append(child)
```

Replace with (append the method):

```python
    def add_block(self, block: MarkdownBlock) -> None:
        """Append a block (roughly one paragraph) to this section."""
        self.blocks.append(block)

    def add_child(self, child: SectionNode) -> None:
        self.children.append(child)

    def accept(self, visitor: MarkdownAstVisitor) -> None:
        """Dispatch this section to ``visitor.walk_section``."""
        visitor.walk_section(self)
```

- [ ] **Step 5: Add `accept` to `DocumentAST`**

In `src/lumberjack/core/models.py`, find `DocumentAST`. It currently ends:

```python
    title: str
    source: str
    root: SectionNode
    metadata: dict[str, Any] = field(default_factory=dict)
    reference_definitions: dict[str, dict[str, str]] = field(default_factory=dict)
```

Replace with (append the method):

```python
    title: str
    source: str
    root: SectionNode
    metadata: dict[str, Any] = field(default_factory=dict)
    reference_definitions: dict[str, dict[str, str]] = field(default_factory=dict)

    def accept(self, visitor: MarkdownAstVisitor) -> None:
        """Dispatch this document to ``visitor.walk_document``."""
        visitor.walk_document(self)
```

- [ ] **Step 6: Run the full test suite to confirm no regressions**

Run: `uv run pytest`
Expected: 191 passed (the new methods are unused so far; nothing breaks).

- [ ] **Step 7: Run ruff lint and format**

Run: `uv run ruff check --fix src/lumberjack/core/models.py && uv run ruff format src/lumberjack/core/models.py`
Expected: no errors. (If ruff complains about an unused `TYPE_CHECKING` import, ignore — it's used in annotations, and `from __future__ import annotations` plus the `TCH` rule handle it.)

- [ ] **Step 8: Commit**

```bash
git add src/lumberjack/core/models.py
git commit -m "feat(models): add accept(visitor) to AST node classes"
```

---

## Task 3: Tests — pruning behavior

**Files:**
- Modify: `tests/test_visitor.py` (append after the last test)

- [ ] **Step 1: Write the section-pruning test**

Append to `tests/test_visitor.py`:

```python


def test_visit_section_returning_false_prunes_children() -> None:
    """visit_section returning False skips its blocks and child sections."""
    document = MarkdownParser().parse(NESTED_FIXTURE, document_title="nested.md")

    class Pruner(MarkdownAstVisitor):
        def __init__(self) -> None:
            self.events: list[tuple[str, str]] = []

        def visit_section(self, section: SectionNode) -> bool | None:
            self.events.append(("enter", section.title))
            # Prune at "Section A" — skip its blocks and Sub A
            if section.title == "Section A":
                return False
            return None

        def depart_section(self, section: SectionNode) -> None:
            self.events.append(("depart", section.title))

    pruner = Pruner()
    pruner.walk_document(document)

    assert ("enter", "Section A") in pruner.events
    assert ("depart", "Section A") in pruner.events  # depart still fires
    # Sub A is a child of Section A — must NOT be visited
    assert ("enter", "Sub A") not in pruner.events
```

- [ ] **Step 2: Run the test to verify it passes**

Run: `uv run pytest tests/test_visitor.py::test_visit_section_returning_false_prunes_children -v`
Expected: PASS.

- [ ] **Step 3: Commit**

```bash
git add tests/test_visitor.py
git commit -m "test(visitor): visit_section False prunes children"
```

- [ ] **Step 4: Write the block-pruning test**

Append to `tests/test_visitor.py`:

```python


def test_visit_block_returning_false_prunes_children() -> None:
    """visit_block returning False skips nested child blocks and inlines."""
    document = MarkdownParser().parse(NESTED_FIXTURE, document_title="nested.md")

    class BlockPruner(MarkdownAstVisitor):
        def __init__(self) -> None:
            self.entered_kinds: list[str] = []
            self.departed_kinds: list[str] = []
            self._prune_depth = 0

        def visit_block(self, block: MarkdownBlock) -> bool | None:
            self.entered_kinds.append(block.kind)
            # Prune list blocks — their list_item children should be skipped
            if block.kind == "list":
                return False
            return None

        def depart_block(self, block: MarkdownBlock) -> None:
            self.departed_kinds.append(block.kind)

    pruner = BlockPruner()
    pruner.walk_document(document)

    assert "list" in pruner.entered_kinds
    assert "list" in pruner.departed_kinds  # depart still fires
    # list_item children of pruned lists must NOT be visited
    list_count = pruner.entered_kinds.count("list")
    list_item_count = pruner.entered_kinds.count("list_item")
    assert list_count >= 1
    assert list_item_count == 0
```

- [ ] **Step 5: Run the test to verify it passes**

Run: `uv run pytest tests/test_visitor.py::test_visit_block_returning_false_prunes_children -v`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add tests/test_visitor.py
git commit -m "test(visitor): visit_block False prunes nested blocks"
```

- [ ] **Step 7: Write the inline-pruning test**

Append to `tests/test_visitor.py`:

```python


def test_visit_inline_returning_false_prunes_children() -> None:
    """visit_inline returning False skips nested inline children."""
    md = "# T\n\nVisit [**example**](https://example.com).\n"
    document = MarkdownParser().parse(md, document_title="inline.md")

    class InlinePruner(MarkdownAstVisitor):
        def __init__(self) -> None:
            self.entered_kinds: list[str] = []
            self.departed_kinds: list[str] = []

        def visit_inline(self, inline: MarkdownInline) -> bool | None:
            self.entered_kinds.append(inline.kind)
            # Prune link inlines — their inner children (strong, text) skipped
            if inline.kind == "link":
                return False
            return None

        def depart_inline(self, inline: MarkdownInline) -> None:
            self.departed_kinds.append(inline.kind)

    pruner = InlinePruner()
    pruner.walk_document(document)

    assert "link" in pruner.entered_kinds
    assert "link" in pruner.departed_kinds  # depart still fires
    # strong is a child of the pruned link — must NOT be visited
    assert "strong" not in pruner.entered_kinds
```

- [ ] **Step 8: Run the test to verify it passes**

Run: `uv run pytest tests/test_visitor.py::test_visit_inline_returning_false_prunes_children -v`
Expected: PASS.

Note: if this fails because the link's inner inline is not `strong` (depends on parser output), inspect the actual inline tree with a quick `print(pruner.entered_kinds)` and adjust the assertion to whatever child kind the pruned link would otherwise contain. Do not change the visitor — adjust the assertion.

- [ ] **Step 9: Commit**

```bash
git add tests/test_visitor.py
git commit -m "test(visitor): visit_inline False prunes nested inlines"
```

- [ ] **Step 10: Write the document-pruning test**

Append to `tests/test_visitor.py`:

```python


def test_visit_document_returning_false_prunes_section_tree() -> None:
    """visit_document returning False skips the entire section tree."""
    document = MarkdownParser().parse(NESTED_FIXTURE, document_title="nested.md")

    class DocPruner(MarkdownAstVisitor):
        def __init__(self) -> None:
            self.events: list[str] = []

        def visit_document(self, document: DocumentAST) -> bool | None:
            self.events.append("enter_document")
            return False  # skip the whole section tree

        def depart_document(self, document: DocumentAST) -> None:
            self.events.append("depart_document")

        def visit_section(self, section: SectionNode) -> bool | None:
            self.events.append(f"enter_section:{section.title}")
            return None

    pruner = DocPruner()
    pruner.walk_document(document)

    assert pruner.events == ["enter_document", "depart_document"]
```

- [ ] **Step 11: Run the test to verify it passes**

Run: `uv run pytest tests/test_visitor.py::test_visit_document_returning_false_prunes_section_tree -v`
Expected: PASS.

- [ ] **Step 12: Commit**

```bash
git add tests/test_visitor.py
git commit -m "test(visitor): visit_document False prunes section tree"
```

- [ ] **Step 13: Write the backward-compat regression test**

Append to `tests/test_visitor.py`:

```python


def test_visit_hooks_returning_none_still_descend() -> None:
    """visit_* hooks that return nothing (None) still descend into children."""
    document = MarkdownParser().parse(NESTED_FIXTURE, document_title="nested.md")

    class NoneReturningVisitor(MarkdownAstVisitor):
        def __init__(self) -> None:
            self.section_count: int = 0

        def visit_section(self, section: SectionNode) -> bool | None:
            self.section_count += 1
            # Explicitly return None — must still descend
            return None

        def visit_block(self, block: MarkdownBlock) -> bool | None:
            return None

        def visit_inline(self, inline: MarkdownInline) -> bool | None:
            return None

    visitor = NoneReturningVisitor()
    visitor.walk_document(document)

    # NESTED_FIXTURE has root + Document + Section A + Sub A + Section B = 5 sections
    assert visitor.section_count == 5
```

- [ ] **Step 14: Run the test to verify it passes**

Run: `uv run pytest tests/test_visitor.py::test_visit_hooks_returning_none_still_descend -v`
Expected: PASS.

- [ ] **Step 15: Commit**

```bash
git add tests/test_visitor.py
git commit -m "test(visitor): None-returning hooks still descend"
```

---

## Task 4: Tests — `accept()` dispatch

**Files:**
- Modify: `tests/test_visitor.py` (append after the pruning tests)

- [ ] **Step 1: Write the `DocumentAST.accept` test**

Append to `tests/test_visitor.py`:

```python


def test_document_accept_equivalent_to_walk_document() -> None:
    """DocumentAST.accept(visitor) produces the same events as walk_document."""
    document = MarkdownParser().parse(NESTED_FIXTURE, document_title="nested.md")

    recorder1 = EventRecorder()
    recorder1.walk_document(document)

    recorder2 = EventRecorder()
    document.accept(recorder2)

    assert recorder1.events == recorder2.events
```

- [ ] **Step 2: Run the test to verify it passes**

Run: `uv run pytest tests/test_visitor.py::test_document_accept_equivalent_to_walk_document -v`
Expected: PASS.

- [ ] **Step 3: Commit**

```bash
git add tests/test_visitor.py
git commit -m "test(visitor): DocumentAST.accept matches walk_document"
```

- [ ] **Step 4: Write the `SectionNode.accept` test**

Append to `tests/test_visitor.py`:

```python


def test_section_accept_starts_traversal_from_arbitrary_section() -> None:
    """SectionNode.accept(visitor) walks that section's subtree."""
    document = MarkdownParser().parse(NESTED_FIXTURE, document_title="nested.md")

    class TitleCollector(MarkdownAstVisitor):
        def __init__(self) -> None:
            self.titles: list[str] = []

        def visit_section(self, section: SectionNode) -> bool | None:
            self.titles.append(section.title)
            return None

    collector = TitleCollector()
    # Start from Section A (first child of the H1 "Document")
    section_a = document.root.children[0].children[0]
    section_a.accept(collector)

    assert collector.titles == ["Section A", "Sub A"]
```

- [ ] **Step 5: Run the test to verify it passes**

Run: `uv run pytest tests/test_visitor.py::test_section_accept_starts_traversal_from_arbitrary_section -v`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add tests/test_visitor.py
git commit -m "test(visitor): SectionNode.accept starts traversal from arbitrary section"
```

- [ ] **Step 7: Write the `MarkdownBlock.accept` test**

Append to `tests/test_visitor.py`:

```python


def test_block_accept_walks_single_block_and_inlines() -> None:
    """MarkdownBlock.accept(visitor) walks that block and its inlines."""
    md = "# T\n\nHello [link](http://x) world.\n"
    document = MarkdownParser().parse(md, document_title="block.md")

    class KindRecorder(MarkdownAstVisitor):
        def __init__(self) -> None:
            self.block_kinds: list[str] = []
            self.inline_kinds: list[str] = []

        def visit_block(self, block: MarkdownBlock) -> bool | None:
            self.block_kinds.append(block.kind)
            return None

        def visit_inline(self, inline: MarkdownInline) -> bool | None:
            self.inline_kinds.append(inline.kind)
            return None

    recorder = KindRecorder()
    # Grab the paragraph block under the H1
    paragraph = document.root.children[0].blocks[0]
    paragraph.accept(recorder)

    assert recorder.block_kinds == ["paragraph"]
    assert "link" in recorder.inline_kinds
    assert "text" in recorder.inline_kinds
```

- [ ] **Step 8: Run the test to verify it passes**

Run: `uv run pytest tests/test_visitor.py::test_block_accept_walks_single_block_and_inlines -v`
Expected: PASS.

Note: if `document.root.children[0].blocks[0]` is not the paragraph (e.g., the heading itself is a block), inspect the actual structure and adjust the index. Do not change the visitor — adjust the index in the test.

- [ ] **Step 9: Commit**

```bash
git add tests/test_visitor.py
git commit -m "test(visitor): MarkdownBlock.accept walks single block"
```

- [ ] **Step 10: Write the `MarkdownInline.accept` test**

Append to `tests/test_visitor.py`:

```python


def test_inline_accept_walks_single_inline_and_children() -> None:
    """MarkdownInline.accept(visitor) walks that inline and its children."""
    md = "# T\n\nHello [**bold link**](http://x).\n"
    document = MarkdownParser().parse(md, document_title="inline-accept.md")

    class InlineRecorder(MarkdownAstVisitor):
        def __init__(self) -> None:
            self.kinds: list[str] = []

        def visit_inline(self, inline: MarkdownInline) -> bool | None:
            self.kinds.append(inline.kind)
            return None

    recorder = InlineRecorder()
    # Get the link inline from the paragraph
    paragraph = document.root.children[0].blocks[0]
    link_inline = next(i for i in paragraph.inlines if i.kind == "link")
    link_inline.accept(recorder)

    assert recorder.kinds[0] == "link"
    # The link has at least one nested child (strong or text)
    assert len(recorder.kinds) >= 2
```

- [ ] **Step 11: Run the test to verify it passes**

Run: `uv run pytest tests/test_visitor.py::test_inline_accept_walks_single_inline_and_children -v`
Expected: PASS.

Note: if the link's first child kind is not `strong` (parser may nest differently), adjust the assertion — the key check is that `accept` walks the link AND its children (len >= 2). Do not change the visitor.

- [ ] **Step 12: Commit**

```bash
git add tests/test_visitor.py
git commit -m "test(visitor): MarkdownInline.accept walks single inline"
```

- [ ] **Step 13: Write the combined accept + pruning test**

Append to `tests/test_visitor.py`:

```python


def test_accept_combined_with_pruning() -> None:
    """accept() entry point respects visit_* pruning."""
    document = MarkdownParser().parse(NESTED_FIXTURE, document_title="combined.md")

    class CombinedVisitor(MarkdownAstVisitor):
        def __init__(self) -> None:
            self.titles: list[str] = []

        def visit_section(self, section: SectionNode) -> bool | None:
            self.titles.append(section.title)
            if section.title == "Sub A":
                return False
            return None

    visitor = CombinedVisitor()
    # Start from Section A via accept; Sub A (its child) should be entered then pruned
    section_a = document.root.children[0].children[0]
    section_a.accept(visitor)

    assert "Section A" in visitor.titles
    assert "Sub A" in visitor.titles  # Sub A is entered (pruning happens at visit)
    # Sub A's children (if any) would be skipped; NESTED_FIXTURE Sub A has a code_fence,
    # so verify no further sections appear under Sub A.
    sub_a_idx = visitor.titles.index("Sub A")
    # After Sub A, no more titles (it's the last in Section A's subtree)
    assert visitor.titles[sub_a_idx:] == ["Sub A"]
```

- [ ] **Step 14: Run the test to verify it passes**

Run: `uv run pytest tests/test_visitor.py::test_accept_combined_with_pruning -v`
Expected: PASS.

- [ ] **Step 15: Commit**

```bash
git add tests/test_visitor.py
git commit -m "test(visitor): accept() respects visit_* pruning"
```

---

## Task 5: Full-suite verification

**Files:** none modified.

- [ ] **Step 1: Run the complete test suite**

Run: `uv run pytest`
Expected: all tests pass (191 existing + 10 new = 201 total).

- [ ] **Step 2: Run full lint and format sweep on the two source files**

Run: `uv run ruff check --fix src/lumberjack/core/visitor.py src/lumberjack/core/models.py tests/test_visitor.py && uv run ruff format src/lumberjack/core/visitor.py src/lumberjack/core/models.py tests/test_visitor.py`
Expected: no errors.

- [ ] **Step 3: Verify the whole codebase still lints**

Run: `uv run ruff check src/ tests/`
Expected: All checks passed.

- [ ] **Step 4: If any changes were made in Steps 2-3, commit them**

Run: `git status`
If clean: done. If any of the three files are modified:

```bash
git add src/lumberjack/core/visitor.py src/lumberjack/core/models.py tests/test_visitor.py
git commit -m "style: ruff format visitor pruning + accept changes"
```

---

## Self-Review

**1. Spec coverage:**
- `visit_*` returns `bool | None`, `False` skips children → Task 1, Steps 1-5. ✓
- `walk_document` gates on `visit_document` (document-level pruning) → Task 1, Step 1. ✓
- `walk_section`/`walk_block`/`walk_inline` gate recursion → Task 1, Steps 2-4. ✓
- `depart_*` always fires → all four walk methods call `self.depart_*(node)` outside the `if descend is not False` block. ✓
- `accept(visitor)` on all four node classes → Task 2, Steps 2-5. ✓
- `MarkdownAstVisitor` under `TYPE_CHECKING` in models.py → Task 2, Step 1. ✓
- Test: section pruning → Task 3, Steps 1-3. ✓
- Test: block pruning → Task 3, Steps 4-6. ✓
- Test: inline pruning → Task 3, Steps 7-9. ✓
- Test: document pruning → Task 3, Steps 10-12. ✓
- Test: backward-compat (None descends) → Task 3, Steps 13-15. ✓
- Test: DocumentAST.accept → Task 4, Steps 1-3. ✓
- Test: SectionNode.accept → Task 4, Steps 4-6. ✓
- Test: MarkdownBlock.accept → Task 4, Steps 7-9. ✓
- Test: MarkdownInline.accept → Task 4, Steps 10-12. ✓
- Test: accept + pruning combined → Task 4, Steps 13-15. ✓
- Out of scope (structured content) deferred to Spec B → explicitly not in this plan. ✓
- Files touched: only visitor.py, models.py, test_visitor.py. ✓

**2. Placeholder scan:** No TBD/TODO. Each test step contains full runnable code. The conditional notes in Task 3 Step 8, Task 4 Steps 8 and 11 give concrete fallbacks (inspect actual structure, adjust assertion, never change the visitor), not placeholders.

**3. Type consistency:**
- `visit_*` return annotation `bool | None` used in Task 1 Step 5 and in every test override that returns `False` or `None`. ✓
- `accept(self, visitor: MarkdownAstVisitor) -> None` consistent across all four node classes in Task 2. ✓
- `MarkdownAstVisitor` imported under `TYPE_CHECKING` in Task 2 Step 1; used only in annotations in Steps 2-5; runtime calls `visitor.walk_*` which already exist. ✓
- The `descend is not False` check is consistent across all four walk methods (Task 1 Steps 1-4) — this correctly treats `None`, `True`, and `0`-ish-but-not-False as "descend"; only literal `False` prunes. ✓
