# Visitor Document-Level Hooks

**Date:** 2026-06-18
**Status:** Approved (design phase)
**Scope:** `src/lumberjack/core/visitor.py`

## Problem

`MarkdownAstVisitor` (in `src/lumberjack/core/visitor.py`) walks the section
tree but has no hook that fires for the document itself. Subclasses therefore
cannot reach `DocumentAST.title`, `DocumentAST.metadata`, or
`DocumentAST.reference_definitions` during a traversal. The visitor is
"technically working" (its 11 tests pass) but in practice a consumer that
wants document-level data must bypass the visitor and read `document` directly,
which defeats the purpose of the abstraction.

The reported gap, confirmed with the user, is: **document-level access**.

Secondary gaps exist (subtree pruning, `accept()`-style dispatch, structured
content walking for tables/code fences) but are explicitly out of scope for
this change so it stays focused and low-risk.

## Goal

Add document enter/depart hooks so a visitor subclass can read and act on
`DocumentAST.title`, `metadata`, and `reference_definitions` as part of a
normal `walk_document` traversal, without breaking the existing visitor API
or its tests.

## Non-Goals

- Subtree pruning (returning `False` / raising to skip children).
- `accept()`-style dispatch where AST nodes own traversal.
- Structured content walking (table cells, code fence internals, math).
- Changes to `walk_section`, `walk_block`, `walk_inline`, or any hook signature.
- Public API changes (`MarkdownAstVisitor` is already re-exported; no change).

## Design

### New Hooks

Two no-op hooks added to `MarkdownAstVisitor`, mirroring the existing
`visit_section` / `depart_section` convention:

```python
def visit_document(self, document: DocumentAST) -> None:
    """Hook called when *entering* a document.

    Read ``document.title``, ``document.metadata``, and
    ``document.reference_definitions`` here before the section tree is walked.
    """

def depart_document(self, document: DocumentAST) -> None:
    """Hook called when the full document tree has been walked.

    Use for finalization (emit collected data, log summaries).
    """
```

### Traversal Order

`walk_document` becomes:

```python
def walk_document(self, document: DocumentAST) -> None:
    self.visit_document(document)      # NEW
    self.walk_section(document.root)   # unchanged
    self.depart_document(document)     # NEW
```

Order: `visit_document` → (full section tree, pre-order as today) →
`depart_document`.

A subclass can now read `document.title` / `document.metadata` /
`document.reference_definitions` in `visit_document` without having to touch
`document.root` directly.

### Unchanged Behavior

- `walk_section`, `walk_block`, `walk_inline` are untouched.
- Existing `visit_*` / `depart_*` hook signatures are untouched.
- Subclasses that do not override `visit_document` / `depart_document`
  produce no document events (the base hooks are no-ops), so the 11 existing
  tests — which assert exact event sequences without overriding the new hooks —
  continue to pass unchanged.

### Type Import

`DocumentAST` is already imported in the `TYPE_CHECKING` block at the top of
`visitor.py` (alongside `SectionNode`, `MarkdownBlock`, `MarkdownInline`), so
no import change is needed. The new usage in `walk_document` and the hook
signatures is annotation-only under `from __future__ import annotations`, so
the existing `TYPE_CHECKING` guard is sufficient; no runtime import is added.

## Test Plan

New tests appended to `tests/test_visitor.py`:

1. **Document hooks fire and bracket the root.** An `EventRecorder` subclass
   that also overrides `visit_document` / `depart_document` records
   `enter_document` / `depart_document` events. Assert the event list starts
   with `enter_document` and ends with `depart_document`, with the existing
   section/block/inline events between them.

2. **Metadata is reachable.** Parse a document with YAML front matter
   (`title: X`). A `MetadataReader(MarkdownAstVisitor)` subclass reads
   `document.metadata` in `visit_document` and asserts `metadata["title"] ==
   "X"`.

3. **Reference definitions are reachable.** Parse a document with a reference
   definition (`[ref]: http://x`). A subclass reads
   `document.reference_definitions` in `visit_document` and asserts the `ref`
   key resolves to `http://x`.

4. **Document title is reachable.** Parse with `document_title="doc.md"`. A
   subclass captures `document.title` in `visit_document` and asserts it
   equals `"doc.md"`.

5. **`depart_document` fires after all children.** A counter subclass
   increments a count in `visit_block` and reads it in `depart_document`;
   assert the count is non-zero (verifies ordering: blocks walked before
   `depart_document`).

6. **Default no-op hooks do not raise.** Bare
   `MarkdownAstVisitor().walk_document(document)` on a minimal document does
   not raise (regression check for the new default methods).

Existing tests in `tests/test_visitor.py` remain unchanged and continue to
pass.

## Files Touched

- `src/lumberjack/core/visitor.py` — add `visit_document` /
  `depart_document` hooks and update `walk_document` to call them. The
  `DocumentAST` import is already present in the `TYPE_CHECKING` block, so no
  import change is required.
- `tests/test_visitor.py` — append the six new tests above.

No changes to `src/lumberjack/__init__.py`, `src/lumberjack/core/__init__.py`,
the parser, the splitter, or any model.

## Risks

- **Breaking change to event sequences?** No. Subclasses that do not override
  the new hooks see no new events. Subclasses that do override them opt in
  explicitly. `AGENTS.md` permits breaking changes, but this change is
  additive.
- **Ordering surprises?** `visit_document` runs before any section/block
  event; `depart_document` runs after all of them. This is the conventional
  enter/children/depart order already used for sections and blocks, so it
  should match user expectations.
