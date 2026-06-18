# Visitor Subtree Pruning + accept() Dispatch

**Date:** 2026-06-18
**Status:** Approved (design phase)
**Scope:** `src/lumberjack/core/visitor.py`, `src/lumberjack/core/models.py`, `tests/test_visitor.py`

**Sequencing:** This is Spec A of two. Spec B (structured-content hooks for
tables/code/math) follows and depends on the `walk_block` changes here.

## Problem

`MarkdownAstVisitor` (`src/lumberjack/core/visitor.py`) has two limitations
that make it impractical for non-trivial tree processing:

1. **No subtree control.** Once `visit_section` / `visit_block` / `visit_inline`
   enters a node, the walker unconditionally recurses into all its children.
   A visitor that wants to stop after the first H2, or skip a known-irrelevant
   `blockquote` subtree, has no way to do so — it must walk the whole tree.

2. **Traversal owned by the visitor only.** The only entry points are
   `walk_document` / `walk_section` / `walk_block` / `walk_inline` on the
   visitor. A caller holding a single `SectionNode` must know to call
   `visitor.walk_section(node)`; the AST nodes themselves carry no traversal
   responsibility. This makes the visitor harder to compose and re-enter.

Document-level pruning is also missing: `visit_document` cannot signal
"skip the section tree."

## Goal

1. Let every `visit_*` hook (including `visit_document`) optionally return
   `False` to skip that node's children. `depart_*` always fires.
2. Add `accept(visitor)` to `DocumentAST`, `SectionNode`, `MarkdownBlock`,
   and `MarkdownInline` so any AST node can be a traversal entry point.
3. Stay backward-compatible: existing hooks that return `None` (the current
   behavior of every hook, including all 17 existing tests) traverse exactly
   as before.

## Non-Goals

- Structured-content hooks (table cells, code/math literals) — Spec B.
- Changing `depart_*` to participate in pruning (depart always fires; the
  pruning signal is only on `visit_*`).
- Rewriting the `walk_*` methods to delegate to `accept()` internally.
  `accept()` is added as an alternative entry point; the `walk_*` methods
  keep their current recursive structure. (Keeps the diff focused.)
- Adding `accept()` support to `MarkdownInline.children` recursion semantics
  changes — inline `accept` just calls `walk_inline`, same as today.

## Design

### Part 1 — Pruning via `visit_*` return value

Every `visit_*` hook may now return `bool | None`:

- Return `False` → skip this node's children (but still call `depart_*`).
- Return `None`, `True`, or nothing → descend normally (current behavior).

The three `walk_*` node methods check the return value of the matching
`visit_*` call before recursing. Example (`walk_section`):

```python
def walk_section(self, section: SectionNode) -> None:
    descend = self.visit_section(section)
    if descend is not False:
        for block in section.blocks:
            self.walk_block(block)
        for child in section.children:
            self.walk_section(child)
    self.depart_section(section)
```

Identical pattern for `walk_block` (gates `block.children` and `block.inlines`)
and `walk_inline` (gates `inline.children`).

**Document-level pruning:** `walk_document` applies the same gate:

```python
def walk_document(self, document: DocumentAST) -> None:
    descend = self.visit_document(document)
    if descend is not False:
        self.walk_section(document.root)
    self.depart_document(document)
```

So `visit_document` returning `False` skips the entire section tree;
`depart_document` still fires.

### Part 2 — Hook return-type annotations

The `visit_*` / `depart_*` signatures change from `-> None` to
`-> bool | None`. This is annotation-only at the base class (the base hooks
keep returning nothing / `None`). The `walk_*` methods consume the value.
`depart_*` hooks keep `-> None` (they don't influence traversal).

```python
def visit_section(self, section: SectionNode) -> bool | None:
    """Hook called when *entering* a section node.

    Return ``False`` to skip this section's blocks and child sections.
    ``depart_section`` still fires.
    """
```

`visit_document`, `visit_section`, `visit_block`, `visit_inline` get the
`-> bool | None` annotation and the docstring note. `depart_*` stay `-> None`.

### Part 3 — `accept()` dispatch on AST nodes

Add `accept(visitor)` to the four node classes in `models.py`:

```python
# DocumentAST
def accept(self, visitor: MarkdownAstVisitor) -> None:
    visitor.walk_document(self)

# SectionNode
def accept(self, visitor: MarkdownAstVisitor) -> None:
    visitor.walk_section(self)

# MarkdownBlock
def accept(self, visitor: MarkdownAstVisitor) -> None:
    visitor.walk_block(self)

# MarkdownInline
def accept(self, visitor: MarkdownAstVisitor) -> None:
    visitor.walk_inline(self)
```

**Import discipline:** `MarkdownAstVisitor` is referenced only in type
annotations, so the import lives under `if TYPE_CHECKING:` in `models.py`
(no runtime import → no circular dependency). The bodies call
`visitor.walk_*` which already exist; no runtime reference to
`MarkdownAstVisitor` is needed.

**Frozen dataclasses:** `DocumentAST`, `MarkdownBlock`, and `MarkdownInline`
are `frozen=True`. Adding a method is fine — methods are class attributes,
not instance state. `SectionNode` is not frozen. No dataclass-field changes
on any node.

**Backward compatibility:** The existing `walk_*` methods stay. Consumers
can use either `visitor.walk_document(doc)` or `doc.accept(visitor)` —
both are public, both behave identically.

### Part 4 — Type import in `visitor.py`

`DocumentAST` is already in the `TYPE_CHECKING` block at the top of
`visitor.py`. No import changes there.

### Part 5 — Module-level `accept()` helper (optional, recommended)

To let callers start a walk without choosing a method, also export a tiny
free function from `visitor.py`:

```python
def walk(node, visitor: MarkdownAstVisitor) -> None:
    """Dispatch ``node.accept(visitor)``; convenience entry point."""
    node.accept(visitor)
```

This lets `walk(doc, visitor)` read as a top-level verb. **Decision: skip
this.** It's sugar, not substance; `node.accept(visitor)` or
`visitor.walk_document(doc)` already read fine. Keep the surface minimal.

## Test Plan

New tests appended to `tests/test_visitor.py`:

**Pruning:**

1. `visit_section` returns `False` → its blocks and child sections are not
   walked; `depart_section` still fires.
2. `visit_block` returns `False` on a `list` → its `list_item` children are
   not walked; `depart_block` still fires.
3. `visit_inline` returns `False` on a `link` → the link's child inlines
   (inner text) are not walked; `depart_inline` still fires.
4. `visit_document` returns `False` → the root section and everything below
   is not walked; `depart_document` still fires.
5. **Backward compat regression:** a visitor whose `visit_*` hooks return
   `None` (no `return` statement) walks the full tree exactly as today
   — covered by the existing 17 tests, but add one explicit test that
   asserts a `visit_section` returning nothing still descends.

**`accept()` dispatch:**

6. `DocumentAST.accept(visitor)` is equivalent to `visitor.walk_document(doc)`
   — same event sequence.
7. `SectionNode.accept(visitor)` starts traversal from an arbitrary section
   (mirrors the existing `walk_section` entry-point test but via `accept`).
8. `MarkdownBlock.accept(visitor)` walks a single block and its inlines.
9. `MarkdownInline.accept(visitor)` walks a single inline and its children.

**Combined:**

10. `accept()` + pruning together: start from a section via `accept`, return
    `False` from one of its child-section `visit_section` calls, verify the
    subtree is pruned.

Existing 17 tests in `tests/test_visitor.py` continue to pass unchanged.

## Files Touched

- `src/lumberjack/core/visitor.py` — gate recursion in `walk_document`,
  `walk_section`, `walk_block`, `walk_inline` on the `visit_*` return value;
  update `visit_document` / `visit_section` / `visit_block` / `visit_inline`
  return annotations to `bool | None` and add the "return False to skip
  children" docstring note.
- `src/lumberjack/core/models.py` — add `accept(visitor)` to `DocumentAST`,
  `SectionNode`, `MarkdownBlock`, `MarkdownInline`; add `MarkdownAstVisitor`
  to the `TYPE_CHECKING` import block.
- `tests/test_visitor.py` — append the pruning + accept tests above.

No changes to `__init__.py`, parsers, splitters, CLI, or web.

## Risks

- **Breaking the return contract?** Additive. Returning `None` (current
  behavior) still descends. Only opt-in `False` prunes. Existing tests and
  external subclasses that don't return are unaffected.
- **Circular import from `accept()`?** Avoided: `MarkdownAstVisitor` is
  imported under `TYPE_CHECKING` in `models.py`; runtime only calls
  `visitor.walk_*`, which already exists. Verified pattern —
  `SplitOptions._default_block_kinds` already does a lazy local import of
  the parser to avoid the same cycle.
- **`frozen=True` dataclasses and methods?** Safe — methods are not
  instance state. No field changes.
- **`accept()` vs `walk_*` dual entry points?** Both are public and behave
  identically. The redundancy is intentional: `accept()` is the
  OO-dispatch idiom; `walk_*` stays for existing callers. No plan to remove
  `walk_*`.
