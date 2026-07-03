# merge_below_ratio + section-flat splitter 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把尾部碎片合并的阈值参数从绝对 token 数（`merge_below_tokens`）改为 `max_tokens` 的比例（`merge_below_ratio`，默认 `0.125`），并把 `SectionSplitter` 的 `subtree_merge` 选项拆成独立的 `section-flat` splitter 变体（不做 subtree-collapse、不做尾部碎片合并）。

**Architecture:**
- `SplitOptions` 字段调整：`merge_below_tokens` → `merge_below_ratio`，移除 `subtree_merge`
- `_merge_small_chunks`（`base.py`）改为现场按 `max_tokens * merge_below_ratio` 算阈值
- `section.py` 新增 `ExactSectionFlatSplitter` / `IncrementalSectionFlatSplitter` 两个类，各自重写整个 `_split_section`（无 subtree-collapse、无 `_merge_small_chunks` 调用）
- registry 新增 `section-flat` / `exact-section-flat` / `incremental-section-flat`
- 公共 API（`lumber()`）、CLI、Web API 同步改名
- 测试与文档全量更新

**Tech Stack:** Python 3.10+, pytest, hatchling, FastAPI

**Spec:** `docs/superpowers/specs/2026-07-03-merge-ratio-and-flat-section-splitters-design.md`

---

## 文件结构

| 文件 | 操作 | 职责 |
|------|------|------|
| `src/lumberjack/core/models.py` | 修改 | `SplitOptions` 字段调整 |
| `src/lumberjack/core/splitters/base.py` | 修改 | `_validate_options` + `_merge_small_chunks` 改读 ratio |
| `src/lumberjack/core/splitters/section.py` | 修改 | 新增 2 个 flat 类，清理 `subtree_merge` 守卫 |
| `src/lumberjack/core/splitters/__init__.py` | 修改 | registry 新增 3 个 flat 名，更新导出 |
| `src/lumberjack/lumber.py` | 修改 | `merge_below_tokens` → `merge_below_ratio` |
| `src/lumberjack/cli.py` | 修改 | CLI flag 改名，`--splitter` choices 补 flat 名 |
| `src/lumberjack/web/routes.py` | 修改 | Web API 字段改名 |
| `tests/test_splitter.py` | 修改 | 更新所有 `merge_below_tokens` 引用，改写 `subtree_merge` 测试 |
| `tests/test_api.py` | 修改 | 更新 `merge_below_tokens` 引用 |
| `tests/test_render_headings.py` | 修改 | 更新 `merge_below_tokens` 引用 |
| `tests/test_token_counting_modes.py` | 修改 | 更新 `merge_below_tokens` 引用 |
| `tests/test_html_table_integration.py` | 修改 | 更新 `merge_below_tokens` 引用 |
| `tests/test_web.py` | 修改 | 更新 `merge_below_tokens` 引用 |
| `tests/test_docx_parser.py` | 修改 | 更新 `merge_below_tokens` 引用 |
| `README.md` | 修改 | option 表 + splitter 表 + 示例 |
| `README.zh-CN.md` | 修改 | 同上（中文） |
| `AGENTS.md` | 修改 | 字段说明、splitter 描述、CLI/Web 段 |
| `docs/recursive-splitter-merges.md` | 修改 | ratio 化示例 |

---

## Task 0: 准备 worktree

**Files:**
- 无文件改动，仅环境准备

- [ ] **Step 1: 确认 `.worktrees/` 存在且被 ignore**

Run:
```bash
cd /home/elery/pypj/lumberjack-private
ls -d .worktrees 2>/dev/null
git check-ignore -q .worktrees && echo "IGNORED" || echo "NOT IGNORED"
```

Expected: 目录存在或不存在都行；如果存在必须输出 `IGNORED`。

- [ ] **Step 2: 如 `.worktrees/` 不存在，创建并加入 .gitignore**

Run（仅当上一步目录不存在时执行）:
```bash
cd /home/elery/pypj/lumberjack-private
mkdir -p .worktrees
grep -qxF '.worktrees/' .gitignore || echo '.worktrees/' >> .gitignore
git add .gitignore
git commit -m "chore: ignore .worktrees/ directory"
```

- [ ] **Step 3: 创建 worktree 与分支**

Run:
```bash
cd /home/elery/pypj/lumberjack-private
git worktree add .worktrees/merge-ratio-flat-section -b feat/merge-ratio-flat-section
```

Expected: `Preparing worktree` / `Creating branch` 成功消息。

- [ ] **Step 4: 进入 worktree 并安装依赖**

Run:
```bash
cd /home/elery/pypj/lumberjack-private/.worktrees/merge-ratio-flat-section
uv sync --group dev --group test --extra tokenizers --extra docx
```

Expected: 依赖安装成功。

- [ ] **Step 5: 跑 baseline 测试确认干净起点**

Run:
```bash
cd /home/elery/pypj/lumberjack-private/.worktrees/merge-ratio-flat-section
uv run pytest -q 2>&1 | tail -20
```

Expected: 全部通过（`X passed`）。如果有失败，停下来报告。

> **后续所有 Task 都在 worktree 目录 `/home/elery/pypj/lumberjack-private/.worktrees/merge-ratio-flat-section` 内执行。**

---

## Task 1: `SplitOptions` 改字段（先写失败测试）

**Files:**
- Test: `tests/test_splitter.py`

- [ ] **Step 1: 在 `tests/test_splitter.py` 末尾追加新字段测试**

在文件末尾追加：

```python


def test_split_options_merge_below_ratio_defaults_to_0_125() -> None:
    assert SplitOptions().merge_below_ratio == 0.125


def test_split_options_merge_below_ratio_rejects_negative() -> None:
    import pytest

    with pytest.raises(ValueError, match="merge_below_ratio"):
        SplitOptions(merge_below_ratio=-0.1)


def test_split_options_merge_below_ratio_rejects_one_or_above() -> None:
    import pytest

    with pytest.raises(ValueError, match="merge_below_ratio"):
        SplitOptions(merge_below_ratio=1.0)
    with pytest.raises(ValueError, match="merge_below_ratio"):
        SplitOptions(merge_below_ratio=1.5)


def test_split_options_has_no_merge_below_tokens_field() -> None:
    field_names = {f.name for f in fields(SplitOptions)}
    assert "merge_below_tokens" not in field_names
    assert "merge_below_ratio" in field_names


def test_split_options_has_no_subtree_merge_field() -> None:
    field_names = {f.name for f in fields(SplitOptions)}
    assert "subtree_merge" not in field_names
```

- [ ] **Step 2: 跑新测试确认失败**

Run:
```bash
cd /home/elery/pypj/lumberjack-private/.worktrees/merge-ratio-flat-section
uv run pytest tests/test_splitter.py -k "merge_below_ratio_defaults or merge_below_ratio_rejects or has_no_merge_below_tokens_field or has_no_subtree_merge_field" -v 2>&1 | tail -30
```

Expected: 全部 FAIL（字段不存在、默认值不对、无校验）。这是预期的——本任务先红后绿。

---

## Task 2: 改 `SplitOptions` 实现

**Files:**
- Modify: `src/lumberjack/core/models.py:183-246`

- [ ] **Step 1: 替换 `SplitOptions` 的字段定义与 docstring**

把 `src/lumberjack/core/models.py` 中 `SplitOptions` 的 docstring + 字段（约 183–230 行）替换为：

```python
@dataclass(slots=True, frozen=True)
class SplitOptions:
    """Parameters controlling how documents are split into chunks.

    Attributes:
        max_tokens: Target maximum token count per chunk.
        ideal_max_tokens_ratio: Ratio of ``max_tokens`` used as the preferred
            split budget before post-processing merge passes. Must be greater
            than 0 and at most 1.
        ideal_max_tokens: Computed as ``max(1, int(max_tokens *
            ideal_max_tokens_ratio))``.  This is the effective split budget
            used during chunking.
        merge_below_ratio: Tail-fragment merge threshold as a fraction of
            ``max_tokens`` in ``[0.0, 1.0)``.  Tail chunks below
            ``int(max_tokens * merge_below_ratio)`` tokens are merged into
            their same-heading predecessor when the result fits
            ``max_tokens``.  ``0.0`` disables merging entirely.  Default
            ``0.125`` (i.e. 12.5% of ``max_tokens``).
        skip_empty_sections: When True, discard chunks that contain only a heading
            with no body content. Chunks with zero rendered tokens are always discarded
            regardless of this setting.
        render_headings: When False, omit only the chunk's ancestor heading
            breadcrumb from the rendered ``Chunk.body`` while keeping the chunk's
            own heading and internal relative headings. Both splitters are
            render-aware: hidden ancestor heading tokens are reclaimed for rendered
            body content, so ``token_count`` measures the final rendered body;
            ``estimated_token_count`` stays close but may differ slightly due
            to join approximations.
        block_options: Per-block-kind configuration. Keys are lowercase block
            kind strings matching :attr:`MarkdownBlock.kind` values; values are
            :class:`BaseParams` instances. Callers that need parser-specific
            defaults should resolve them before constructing
            :class:`SplitOptions`.
        standalone_kinds: Block kinds marked as isolated (cached).
    """

    max_tokens: int = 1200
    ideal_max_tokens_ratio: float = 0.8
    merge_below_ratio: float = 0.125
    skip_empty_sections: bool = True
    render_headings: bool = True
    block_options: dict[str, BaseParams] = field(default_factory=dict)

    # Cached derived fields — computed in __post_init__.
    ideal_max_tokens: int = field(init=False, repr=False)
    standalone_kinds: frozenset[str] = field(init=False, repr=False)

    def __post_init__(self) -> None:
        if not (0.0 <= self.merge_below_ratio < 1.0):
            raise ValueError(
                f"merge_below_ratio must be in [0.0, 1.0), got {self.merge_below_ratio}"
            )
        object.__setattr__(
            self,
            "ideal_max_tokens",
            max(1, int(self.max_tokens * self.ideal_max_tokens_ratio)),
        )
        object.__setattr__(
            self,
            "standalone_kinds",
            frozenset(kind for kind, cfg in self.block_options.items() if cfg.isolated),
        )
```

- [ ] **Step 2: 跑 Task 1 的测试确认通过**

Run:
```bash
cd /home/elery/pypj/lumberjack-private/.worktrees/merge-ratio-flat-section
uv run pytest tests/test_splitter.py -k "merge_below_ratio_defaults or merge_below_ratio_rejects or has_no_merge_below_tokens_field or has_no_subtree_merge_field" -v 2>&1 | tail -15
```

Expected: 5 passed。

- [ ] **Step 3: 不 commit**——本任务与 Task 3、4、5、6、7 在同一个原子提交里（中间状态 type check 不通过，因为下游消费方仍引用 `merge_below_tokens` / `subtree_merge`）。

---

## Task 3: 改 `_validate_options` 与 `_merge_small_chunks`（`base.py`）

**Files:**
- Modify: `src/lumberjack/core/splitters/base.py:170-190`（`_validate_options`）
- Modify: `src/lumberjack/core/splitters/base.py:283-320`（`_merge_small_chunks`）

- [ ] **Step 1: 替换 `_validate_options` 中的 `merge_below_tokens` 校验**

把 `_validate_options` 整个方法（`base.py` 约 170–189 行）替换为：

```python
    def _validate_options(self) -> None:
        if self.options.max_tokens <= 0:
            raise ValueError("max_tokens must be greater than 0")
        if not 0 < self.options.ideal_max_tokens_ratio <= 1:
            raise ValueError(
                "ideal_max_tokens_ratio must be greater than 0 and at most 1"
            )
        if not (0.0 <= self.options.merge_below_ratio < 1.0):
            raise ValueError(
                f"merge_below_ratio must be in [0.0, 1.0), "
                f"got {self.options.merge_below_ratio}"
            )
        for kind, cfg in self.options.block_options.items():
            if cfg.max_tokens is not None and cfg.max_tokens <= 0:
                raise ValueError(
                    f"block_options[{kind!r}].max_tokens must be positive, got {cfg.max_tokens}"
                )
```

- [ ] **Step 2: 替换 `_merge_small_chunks` 的阈值来源**

把 `_merge_small_chunks` 开头的 `merge_below` 计算（`base.py` 约 289–294 行）替换。整个方法（约 283–320 行）替换为：

```python
    def _merge_small_chunks(
        self,
        chunks: list[ChunkDraft],
        *,
        parent_headings: HeadingPath | None = None,
    ) -> list[ChunkDraft]:
        """Merge adjacent same-parent chunks below the merge threshold, bottom-up.

        Threshold = ``int(max_tokens * merge_below_ratio)``; ``merge_below_ratio == 0``
        disables merging entirely.
        """
        merge_below = int(self.options.max_tokens * self.options.merge_below_ratio)
        if merge_below <= 0:
            return chunks
        if not chunks:
            return chunks

        merged: list[ChunkDraft] = list(chunks)
        i = len(merged) - 1
        while i > 0:
            current = merged[i]
            previous = merged[i - 1]
            can_merge = (
                (parent_headings is None or previous.headings == parent_headings)
                and previous.headings == current.headings
                and current.entries
            )
            if (
                can_merge
                and self._draft_budget_tokens(current) < merge_below
                and previous.chunk_type == "paragraph"
                and current.chunk_type == "paragraph"
            ):
                merged_draft = self._merge_drafts(previous, current)
                # Compare the rendered footprint against max_tokens.  Because
                # can_merge guarantees previous.headings == current.headings,
                # the merged common prefix is that shared path.
                if self._draft_budget_tokens(merged_draft) <= self.options.max_tokens:
                    merged[i - 1] = merged_draft
                    del merged[i]
            i -= 1
        return merged
```

- [ ] **Step 3: 不跑测试**——下游 `section.py` / `recursive.py`（无引用） / 公共 API 还在引用 `merge_below_tokens`，type check 不过；统一在 Task 8 跑。

---

## Task 4: `section.py` 新增 flat 类 + 清理守卫

**Files:**
- Modify: `src/lumberjack/core/splitters/section.py`

- [ ] **Step 1: 在 `ExactSectionSplitter._split_section` 中删除 `subtree_merge` 守卫**

把 `section.py` 第 43 行的 `if self.options.subtree_merge:` 整个守卫去掉（**保留**守卫内的逻辑，**只删** `if self.options.subtree_merge:` 这一行及其带来的多一级缩进）。

修改后 `ExactSectionSplitter._split_section` 应该是（约 32–100 行，注意缩进变化）：

```python
    def _split_section(self, section: SectionNode) -> list[ChunkDraft]:
        """Return one direct-body draft per section, then recurse into children.

        Short-circuit: if the entire subtree (own body + all descendants) fits
        within ``ideal_max_tokens`` and contains no standalone block, collapse
        it into a single chunk.  Otherwise fall through to the per-section
        split path below (unchanged).
        """
        if not (section.blocks or section.children or section.level > 0):
            return []

        body_has_standalone = any(
            b.kind in self.options.standalone_kinds for b in section.blocks
        )
        child_has_standalone = any(
            self._section_has_standalone(child) for child in section.children
        )
        if not body_has_standalone and not child_has_standalone:
            entries = self._entries_from_section(section)
            common = common_heading_path(entry.headings for entry in entries)
            single = self._draft_from_entries(entries, common, origin="section")
            if self._draft_budget_tokens(single) <= self.options.ideal_max_tokens:
                return [single]

        chunks: list[ChunkDraft] = []
        standalone_kinds = self.options.standalone_kinds

        if section.blocks or section.level > 0:
            body_has_standalone = any(
                b.kind in standalone_kinds for b in section.blocks
            )
            body = join_markdown([b.text for b in section.blocks])
            body_tokens = self.tokenizer.count(body, cache=True)
            body_budget = self._exact_body_budget(section.path)
            should_split_body = body_has_standalone or body_tokens > body_budget
            if should_split_body:
                body_chunks = self._split_section_body(section)
                chunks.extend(
                    self._merge_small_chunks(body_chunks, parent_headings=section.path)
                )
            else:
                entry = Entry(
                    headings=section.path,
                    body=body,
                    start_line=self._min_start_lines(section.blocks),
                    end_line=self._max_end_lines(section.blocks),
                    body_token_count=body_tokens,
                )
                headings_token_count = self._heading_budget_token_count(section.path)
                chunks.append(
                    ChunkDraft(
                        entries=[entry],
                        headings=section.path,
                        headings_token_count=headings_token_count,
                        body_token_count=body_tokens,
                        token_count=headings_token_count + body_tokens,
                    )
                )

        for child in section.children:
            chunks.extend(self._split_section(child))

        return chunks
```

- [ ] **Step 2: 在 `IncrementalSectionSplitter._split_section` 中删除 `subtree_merge` 守卫**

把 `section.py` 第 132 行的 `if self.options.subtree_merge and section.can_emit_as_single_chunk:` 改为 `if section.can_emit_as_single_chunk:`（去掉 `self.options.subtree_merge and`）。

- [ ] **Step 3: 新增 `ExactSectionFlatSplitter` 类**

在 `IncrementalSectionSplitter` 类定义之后（约 185 行）、`SectionSplitter = ExactSectionSplitter` 别名之前，插入两个新类与别名：

```python


class ExactSectionFlatSplitter(ExactCountingMixin, BaseSplitter):
    """Per-heading section splitter without subtree-collapse or tail merging.

    Emits one chunk per heading section's direct body and recurses into
    children.  Unlike :class:`ExactSectionSplitter`, this variant:

    1. Never collapses an entire subtree into a single chunk (no
       subtree-collapse short-circuit).
    2. Never calls :meth:`_merge_small_chunks` — tail-fragment merging is
       fully disabled in this variant, regardless of ``merge_below_ratio``.

    Oversized section bodies are still split by token budget respecting
    ``block_options`` (standalone isolation, splittable kinds, per-block
    budgets).  Every budget decision fully recounts the rendered candidate
    text.

    Registered as ``"section-flat"`` and ``"exact-section-flat"``.
    Works with any Tokenizer.
    """

    def _split_section(self, section: SectionNode) -> list[ChunkDraft]:
        """Return one direct-body draft per section, then recurse into children.

        No subtree-collapse short-circuit and no tail-fragment merging.
        """
        if not (section.blocks or section.children or section.level > 0):
            return []

        chunks: list[ChunkDraft] = []
        standalone_kinds = self.options.standalone_kinds

        if section.blocks or section.level > 0:
            body_has_standalone = any(
                b.kind in standalone_kinds for b in section.blocks
            )
            body = join_markdown([b.text for b in section.blocks])
            body_tokens = self.tokenizer.count(body, cache=True)
            body_budget = self._exact_body_budget(section.path)
            should_split_body = body_has_standalone or body_tokens > body_budget
            if should_split_body:
                body_chunks = self._split_section_body(section)
                chunks.extend(body_chunks)
            else:
                entry = Entry(
                    headings=section.path,
                    body=body,
                    start_line=self._min_start_lines(section.blocks),
                    end_line=self._max_end_lines(section.blocks),
                    body_token_count=body_tokens,
                )
                headings_token_count = self._heading_budget_token_count(section.path)
                chunks.append(
                    ChunkDraft(
                        entries=[entry],
                        headings=section.path,
                        headings_token_count=headings_token_count,
                        body_token_count=body_tokens,
                        token_count=headings_token_count + body_tokens,
                    )
                )

        for child in section.children:
            chunks.extend(self._split_section(child))

        return chunks


class IncrementalSectionFlatSplitter(IncrementalCountingMixin, BaseSplitter):
    """Per-heading section splitter (incremental estimate) without subtree-collapse or tail merging.

    Same per-section topology as :class:`ExactSectionFlatSplitter`, but uses
    the additive incremental estimate path: the subtree is pre-measured and
    budget decisions use a running estimate rather than full rendered
    recounts.

    No subtree-collapse short-circuit and no tail-fragment merging.

    Registered as ``"incremental-section-flat"``.  Works with any Tokenizer.
    """

    def _split_section(
        self,
        section: MeasuredSection,
    ) -> list[ChunkDraft]:
        """Return one direct-body draft per section, then recurse into children.

        No subtree-collapse short-circuit and no tail-fragment merging.
        """
        node = section.node
        if not (node.blocks or section.children or node.level > 0):
            return []

        chunks: list[ChunkDraft] = []

        if node.blocks or node.level > 0:
            body_has_standalone = any(
                b.kind in self.options.standalone_kinds for b in node.blocks
            )
            if (
                body_has_standalone
                or section.counts.body > self.options.ideal_max_tokens
            ):
                body_chunks = self._split_section_body(section)
                chunks.extend(body_chunks)
            else:
                entry = self._entry_from_blocks(
                    node.path,
                    node.blocks,
                    body_token_count=section.counts.body,
                )
                headings_token_count = self._heading_budget_token_count(node.path)
                chunks.append(
                    ChunkDraft(
                        entries=[entry],
                        headings=node.path,
                        headings_token_count=headings_token_count,
                        body_token_count=section.counts.body,
                        token_count=headings_token_count + section.counts.body,
                    )
                )

        for child in section.children:
            chunks.extend(self._split_section(child))

        return chunks


# Backward-compatible alias: the default ``section`` splitter is the exact one.
SectionSplitter = ExactSectionSplitter
SectionFlatSplitter = ExactSectionFlatSplitter

__all__ = [
    "ExactSectionSplitter",
    "ExactSectionFlatSplitter",
    "IncrementalSectionSplitter",
    "IncrementalSectionFlatSplitter",
    "SectionSplitter",
    "SectionFlatSplitter",
]
```

注意：上面替换会把原有的 `# Backward-compatible alias: ...` 单行和原 `__all__` 一起覆盖；确保删除原 `SectionSplitter = ExactSectionSplitter` 行和原 `__all__ = [...]`，由上面新版本替代。

---

## Task 5: registry 更新（`__init__.py`）

**Files:**
- Modify: `src/lumberjack/core/splitters/__init__.py`

- [ ] **Step 1: 更新 import 与 registry**

把 `src/lumberjack/core/splitters/__init__.py` 的 `from .section import ...` 和 `SPLITTER_REGISTRY` 替换为：

```python
from .section import (
    ExactSectionFlatSplitter,
    ExactSectionSplitter,
    IncrementalSectionFlatSplitter,
    IncrementalSectionSplitter,
    SectionFlatSplitter,
    SectionSplitter,
)
```

（替换原 `from .section import ...` 块）

```python
SPLITTER_REGISTRY: dict[str, type[BaseSplitter]] = {
    "recursive": ExactRecursiveSplitter,
    "exact-recursive": ExactRecursiveSplitter,
    "incremental-recursive": IncrementalRecursiveSplitter,
    "section": ExactSectionSplitter,
    "exact-section": ExactSectionSplitter,
    "section-flat": ExactSectionFlatSplitter,
    "exact-section-flat": ExactSectionFlatSplitter,
    "incremental-section": IncrementalSectionSplitter,
    "incremental-section-flat": IncrementalSectionFlatSplitter,
}
```

- [ ] **Step 2: 更新 `create_splitter` docstring 与 `__all__`**

把 `create_splitter` 函数 docstring 中的 splitter 名清单更新为：

```python
    """Instantiate a splitter by name.

    Args:
        name: Splitter name.  One of ``"recursive"`` (alias for
            ``"exact-recursive"``, the default), ``"section"`` (alias for
            ``"exact-section"``), ``"section-flat"`` (alias for
            ``"exact-section-flat"``), ``"exact-recursive"``,
            ``"incremental-recursive"``, ``"exact-section"``,
            ``"incremental-section"``, ``"exact-section-flat"``, or
            ``"incremental-section-flat"``.  Exact splitters fully recount
            rendered text at every budget decision; incremental splitters
            use an additive estimate + 8-char separator-delta window.
            ``section-flat`` variants disable subtree-collapse and
            tail-fragment merging.
        tokenizer: Tokenizer engine.  Defaults to :class:`ApproxCharTokenizer`.
        options: Split options.

    Raises:
        ValueError: If *name* is not a registered splitter.
    """
```

把 `__all__` 更新为：

```python
__all__ = [
    "SPLITTER_REGISTRY",
    "BaseSplitter",
    "ExactRecursiveSplitter",
    "ExactSectionFlatSplitter",
    "ExactSectionSplitter",
    "IncrementalRecursiveSplitter",
    "IncrementalSectionFlatSplitter",
    "IncrementalSectionSplitter",
    "RecursiveSplitter",
    "SectionFlatSplitter",
    "SectionSplitter",
    "create_splitter",
]
```

---

## Task 6: 公共 API（`lumber.py`）

**Files:**
- Modify: `src/lumberjack/lumber.py`

- [ ] **Step 1: 改函数签名与 docstring**

把 `src/lumberjack/lumber.py` 第 21 行的 `merge_below_tokens: int | None = 50,` 改为：

```python
    merge_below_ratio: float = 0.125,
```

把对应 docstring（第 45–47 行）替换为：

```python
        merge_below_ratio: Tail-fragment merge threshold as a fraction of
            ``max_tokens`` in ``[0.0, 1.0)``.  Tail chunks below
            ``int(max_tokens * merge_below_ratio)`` tokens are merged into
            their same-heading predecessor when the result fits
            ``max_tokens``.  ``0.0`` disables merging entirely.
            Default ``0.125``.
```

- [ ] **Step 2: 改 `SplitOptions(...)` 构造**

把第 122 行 `merge_below_tokens=merge_below_tokens,` 改为：

```python
        merge_below_ratio=merge_below_ratio,
```

- [ ] **Step 3: 更新 `splitter` docstring 加 flat 名**

把 `lumber.py` 中 `splitter` 参数 docstring（约 57–61 行）替换为：

```python
        splitter: Built-in splitter name. ``"recursive"`` (default) and
            ``"section"`` alias the exact (full-recount) variants; the
            explicit names ``"exact-recursive"``, ``"incremental-recursive"``,
            ``"exact-section"``, ``"incremental-section"``,
            ``"exact-section-flat"``, and ``"incremental-section-flat"``
            select the counting strategy directly. ``section-flat`` variants
            disable subtree-collapse and tail-fragment merging.
```

---

## Task 7: CLI（`cli.py`）

**Files:**
- Modify: `src/lumberjack/cli.py`

- [ ] **Step 1: 替换 `--merge-below-tokens` flag**

把 `cli.py` 第 63–69 行的 `--merge-below-tokens` 参数替换为：

```python
    parser.add_argument(
        "--merge-below-ratio",
        type=float,
        default=0.125,
        help="Tail-fragment merge threshold as a fraction of --max-tokens "
        "in [0.0, 1.0); 0 disables merging (default: 0.125)",
    )
```

- [ ] **Step 2: 在 `--splitter` choices 中加 flat 名**

把 `cli.py` 第 38–53 行 `--splitter` 的 `choices` 元组替换为：

```python
        choices=(
            "recursive",
            "section",
            "section-flat",
            "exact-recursive",
            "incremental-recursive",
            "exact-section",
            "incremental-section",
            "exact-section-flat",
            "incremental-section-flat",
        ),
```

- [ ] **Step 3: 改 `lumber(...)` 调用**

把 `cli.py` 第 120 行 `merge_below_tokens=args.merge_below_tokens,` 改为：

```python
        merge_below_ratio=args.merge_below_ratio,
```

---

## Task 8: Web API（`web/routes.py`）

**Files:**
- Modify: `src/lumberjack/web/routes.py`

- [ ] **Step 1: 改 `TextSplitRequest` 字段**

把 `routes.py` 第 22 行 `merge_below_tokens: int | None = 50` 改为：

```python
    merge_below_ratio: float = 0.125
```

- [ ] **Step 2: 改 `split_text` 中的 `lumber(...)` 调用**

把 `routes.py` 第 80 行 `merge_below_tokens=payload.merge_below_tokens,` 改为：

```python
            merge_below_ratio=payload.merge_below_ratio,
```

- [ ] **Step 3: 改 `split_file` Form 参数**

把 `routes.py` 第 104 行 `merge_below_tokens: int | None = Form(50),` 改为：

```python
    merge_below_ratio: float = Form(0.125),
```

- [ ] **Step 4: 改 `split_file` 中的 `lumber(...)` 调用**

把 `routes.py` 第 139 行 `merge_below_tokens=merge_below_tokens,` 改为：

```python
            merge_below_ratio=merge_below_ratio,
```

---

## Task 9: 全量 type check（验证 Task 2–8 的原子改动）

**Files:**
- 无文件改动

- [ ] **Step 1: ty check**

Run:
```bash
cd /home/elery/pypj/lumberjack-private/.worktrees/merge-ratio-flat-section
uv run ty check . 2>&1 | tail -30
```

Expected: 无 error。如果有 error 指向 `merge_below_tokens` / `subtree_merge` 残留引用，定位并修复（grep 全仓）。

- [ ] **Step 2: grep 全仓确认无残留引用**

Run:
```bash
cd /home/elery/pypj/lumberjack-private/.worktrees/merge-ratio-flat-section
grep -rn "merge_below_tokens\|subtree_merge" src/ 2>&1 | grep -v "\.pyc"
```

Expected: 无输出（src 中应该没有任何 `merge_below_tokens` 或 `subtree_merge` 引用）。

> 注：tests/ 和 docs/ 中的引用在后续 Task 处理，本步只查 src/。

---

## Task 10: 更新 `tests/test_splitter.py` 的 `merge_below_tokens` 引用

**Files:**
- Modify: `tests/test_splitter.py`

这一任务批量更新所有 `merge_below_tokens=...` 为 `merge_below_ratio=...`，并改写 `subtree_merge` 相关测试。

- [ ] **Step 1: 找出所有需要改的位置**

Run:
```bash
cd /home/elery/pypj/lumberjack-private/.worktrees/merge-ratio-flat-section
grep -n "merge_below_tokens\|subtree_merge" tests/test_splitter.py
```

记录所有行号。

- [ ] **Step 2: 把所有 `merge_below_tokens=0` 改成 `merge_below_ratio=0.0`**

把所有形如 `merge_below_tokens=0` 的（包括 `=0,` `=0)` 等）替换为 `merge_below_ratio=0.0`。这一步可以用 `Edit` 工具的 `replace_all`，但因为前后文不同，需要逐处确认。最简单的策略：

对每个出现 `merge_below_tokens=0` 的地方，先 Read 该行上下文（约 ±3 行），然后 Edit 把整行改成 `merge_below_ratio=0.0`（保留行内其它内容如逗号、括号）。

例（`tests/test_splitter.py:2226`）：
- 旧：`        options=SplitOptions(max_tokens=200, merge_below_tokens=0),`
- 新：`        options=SplitOptions(max_tokens=200, merge_below_ratio=0.0),`

- [ ] **Step 3: 把 `merge_below_tokens=-1` 改成 `merge_below_ratio=0.0`**

`-1` 和 `0` 都表示禁用，统一改成 `merge_below_ratio=0.0`。

例（`tests/test_splitter.py:789`）：
- 旧：`            merge_below_tokens=-1,`
- 新：`            merge_below_ratio=0.0,`

- [ ] **Step 4: 把 `merge_below_tokens=None` 改成 `merge_below_ratio=0.0`**

例（`tests/test_splitter.py:877`）：
- 旧：`            merge_below_tokens=None,`
- 新：`            merge_below_ratio=0.0,`

对应测试函数名 `test_merge_below_tokens_none_disables_merging` 改为 `test_merge_below_ratio_zero_disables_merging`。

- [ ] **Step 5: 把 `merge_below_tokens=N`（N>0）改成 `merge_below_ratio=N/max_tokens`**

按每个测试的 `max_tokens` 上下文换算：

- `tests/test_splitter.py:333` —— `max_tokens=40, merge_below_tokens=39` → `max_tokens=40, merge_below_ratio=0.975`
- `tests/test_splitter.py:376` —— 找该处 `max_tokens` 值；如 `max_tokens=200, merge_below_tokens=80` → `merge_below_ratio=0.4`（按实际 max_tokens 换算）
- `tests/test_splitter.py:812` —— `max_tokens=30, merge_below_tokens=29` → `merge_below_ratio=29/30`（用 `0.967` 或更精确的小数；为安全起见用分数计算后的浮点，如 `29/30` Python 会算出 `0.9666...`，写 `0.967` 即可——但 0.967*30=29.01，int 后 29，OK）
- `tests/test_splitter.py:832` —— `max_tokens=40, merge_below_tokens=39` → `merge_below_ratio=0.975`
- `tests/test_splitter.py:855`（`test_merge_below_tokens_does_not_merge_past_rendered_budget`）—— `max_tokens=60, merge_below_tokens=10` → `merge_below_ratio=10/60`（写 `0.167`，0.167*60=10.02，int 后 10，OK）

> **每个改完后立即在脑海里验证：**`int(max_tokens * new_ratio)` 应等于原 `merge_below_tokens` 值。若不等，调整 ratio 精度。例如 `max_tokens=60, merge_below_tokens=10`：`0.167 * 60 = 10.02 → int = 10 ✓`；`0.166 * 60 = 9.96 → int = 9 ✗`。

> 对应测试函数名建议改名：
> - `test_merge_below_tokens_does_not_merge_past_rendered_budget` → `test_merge_below_ratio_does_not_merge_past_rendered_budget`

- [ ] **Step 6: 删除 `test_split_options_subtree_merge_defaults_true`**

删除 `tests/test_splitter.py` 中整个函数：

```python
def test_split_options_subtree_merge_defaults_true() -> None:
    assert SplitOptions().subtree_merge is True
```

- [ ] **Step 7: 改写 `test_section_splitter_subtree_merge_option_controls_behavior`**

把整个函数（`tests/test_splitter.py:2247`）替换为：

```python
def test_section_vs_section_flat_splitter_behavior() -> None:
    """`section` collapses a fitting subtree; `section-flat` keeps per-section."""
    fixture = """# Parent

Parent intro.

## One

One body.

## Two

Two body.
"""
    document = MarkdownParser().parse(fixture, document_title="t.md")

    merged = SectionSplitter(
        tokenizer=CharacterTokenizer(),
        options=SplitOptions(max_tokens=1000, merge_below_ratio=0.0),
    ).split(document)
    assert len(merged) == 1
    assert merged[0].headings == ((1, "Parent"),)
    assert "## One" in merged[0].body
    assert "## Two" in merged[0].body

    from lumberjack.core.splitters import ExactSectionFlatSplitter

    per_section = ExactSectionFlatSplitter(
        tokenizer=CharacterTokenizer(),
        options=SplitOptions(max_tokens=1000, merge_below_ratio=0.0),
    ).split(document)
    # section-flat: three chunks, one per section.  The "# Parent" body
    # lives under the document root (level 0), so its headings tuple is
    # empty under ancestor-heading rendering.
    assert len(per_section) == 3
    assert per_section[0].headings == ()
    assert per_section[1].headings == ((1, "Parent"),)
    assert per_section[2].headings == ((1, "Parent"),)
    assert per_section[0].body == "# Parent\n\nParent intro."
    assert per_section[1].body == "# Parent\n\n## One\n\nOne body."
    assert per_section[2].body == "# Parent\n\n## Two\n\nTwo body."
```

- [ ] **Step 8: 改写 `test_incremental_section_splitter_subtree_merge_option_controls_behavior`**

把整个函数（`tests/test_splitter.py:2290`）替换为：

```python
def test_incremental_section_vs_flat_splitter_behavior() -> None:
    """IncrementalSectionFlatSplitter behaves like ExactSectionFlatSplitter."""
    fixture = """# Parent

Parent intro.

## One

One body.

## Two

Two body.
"""
    document = MarkdownParser().parse(fixture, document_title="t.md")

    merged = IncrementalSectionSplitter(
        tokenizer=CharacterTokenizer(),
        options=SplitOptions(max_tokens=1000, merge_below_ratio=0.0),
    ).split(document)
    assert len(merged) == 1
    assert merged[0].headings == ((1, "Parent"),)

    from lumberjack.core.splitters import IncrementalSectionFlatSplitter

    per_section = IncrementalSectionFlatSplitter(
        tokenizer=CharacterTokenizer(),
        options=SplitOptions(max_tokens=1000, merge_below_ratio=0.0),
    ).split(document)
    assert len(per_section) == 3
    assert per_section[0].headings == ()
    assert per_section[1].headings == ((1, "Parent"),)
    assert per_section[2].headings == ((1, "Parent"),)
```

- [ ] **Step 9: 改写 `test_subtree_merge_false_still_splits_standalone_blocks`**

把整个函数（`tests/test_splitter.py:2325`）替换为：

```python
def test_section_flat_still_splits_standalone_blocks() -> None:
    """section-flat still routes standalone blocks through body splitting."""
    fixture = """# Parent

| A | B |
|---|---|
| 1 | 2 |

## One

One body.
"""
    document = MarkdownParser().parse(fixture, document_title="t.md")
    from lumberjack.core.splitters import ExactSectionFlatSplitter

    splitter = ExactSectionFlatSplitter(
        tokenizer=CharacterTokenizer(),
        options=SplitOptions(
            max_tokens=10000,
            merge_below_ratio=0.0,
            block_options=markdown_block_options(
                {"table": BaseParams(isolated=True)},
            ),
        ),
    )

    chunks = splitter.split(document)

    # Standalone table forces its own chunk regardless of flat mode.
    assert len(chunks) >= 2
    assert any("| A |" in c.body for c in chunks)
```

- [ ] **Step 10: 改写 `test_section_splitter_subtree_merge_does_not_cross_top_level_sections`**

把该函数体内 `merge_below_tokens=0` 改成 `merge_below_ratio=0.0`（`tests/test_splitter.py:2226`）。函数名可保留（描述的是 section 默认行为不跨顶层），但为避免误导可改名为 `test_section_splitter_does_not_cross_top_level_sections`。**改名**：

把整个函数（`tests/test_splitter.py:2204`）的函数名行改为：

```python
def test_section_splitter_does_not_cross_top_level_sections() -> None:
```

并把 docstring 中 "subtree_merge" / "subtree-merge" 字样改为中性表述（"section splitter"），同时把 `merge_below_tokens=0` 改成 `merge_below_ratio=0.0`。

- [ ] **Step 11: 跑 test_splitter.py 全部测试**

Run:
```bash
cd /home/elery/pypj/lumberjack-private/.worktrees/merge-ratio-flat-section
uv run pytest tests/test_splitter.py -v 2>&1 | tail -40
```

Expected: 全部 passed。如果有 FAIL，定位并修复（通常是 ratio 精度问题或漏改的 `merge_below_tokens`/`subtree_merge` 引用）。

---

## Task 11: 更新其他测试文件的 `merge_below_tokens` 引用

**Files:**
- Modify: `tests/test_api.py`
- Modify: `tests/test_render_headings.py`
- Modify: `tests/test_token_counting_modes.py`
- Modify: `tests/test_html_table_integration.py`
- Modify: `tests/test_web.py`
- Modify: `tests/test_docx_parser.py`

- [ ] **Step 1: 找出所有引用**

Run:
```bash
cd /home/elery/pypj/lumberjack-private/.worktrees/merge-ratio-flat-section
grep -rn "merge_below_tokens\|subtree_merge" tests/ 2>&1 | grep -v "test_splitter.py"
```

- [ ] **Step 2: 把所有 `merge_below_tokens=-1` / `=None` / `=0` 改成 `merge_below_ratio=0.0`**

按文件处理。每个文件需要单独 Read + Edit。

**`tests/test_api.py`**（约 4 处，全部 `=-1`）：
- `lumber(..., merge_below_tokens=-1)` → `lumber(..., merge_below_ratio=0.0)`

**`tests/test_render_headings.py`**（约 6 处，全部 `=0`）：
- `merge_below_tokens=0` → `merge_below_ratio=0.0`

**`tests/test_token_counting_modes.py`**（2 处）：
- 第 170 行：`max_tokens=20, merge_below_tokens=10` → `merge_below_ratio=0.5`（0.5*20=10，int=10 ✓）
- 第 235 行：`max_tokens=40, merge_below_tokens=10` → `merge_below_ratio=0.25`（0.25*40=10，int=10 ✓）

**`tests/test_html_table_integration.py`**（约 2 处，`=-1`）：
- `merge_below_tokens=-1` → `merge_below_ratio=0.0`

**`tests/test_web.py`**（约 2 处，`=-1`，是 JSON payload）：
- JSON 中的 `"merge_below_tokens": -1` → `"merge_below_ratio": 0.0`

**`tests/test_docx_parser.py`**（约 1 处，`=20`，`max_tokens=200`）：
- `merge_below_tokens=20` → `merge_below_ratio=0.1`（0.1*200=20，int=20 ✓）

- [ ] **Step 3: 跑这些测试文件**

Run:
```bash
cd /home/elery/pypj/lumberjack-private/.worktrees/merge-ratio-flat-section
uv run pytest tests/test_api.py tests/test_render_headings.py tests/test_token_counting_modes.py tests/test_html_table_integration.py tests/test_web.py tests/test_docx_parser.py -v 2>&1 | tail -40
```

Expected: 全部 passed。

---

## Task 12: 新增测试覆盖新行为

**Files:**
- Modify: `tests/test_splitter.py`

- [ ] **Step 1: 在 `tests/test_splitter.py` 末尾追加新测试**

```python


def test_merge_below_ratio_threshold_derived_from_max_tokens() -> None:
    """merge_below_ratio 的阈值 = int(max_tokens * ratio)，控制尾部碎片是否合并。

    构造一个 body 超过 ideal_max_tokens 的 section，强制 _split_section_body
    切出多块。尾部碎片小于阈值时合并、大于阈值时不合并。
    用 CharacterTokenizer (1 char = 1 token) 精确控制大小。
    """
    # body = "# A\n\n" + "x " * 31 + "\n\n" + "y"
    # 总 ~67 tokens；max_tokens=60, ideal_max_tokens_ratio=1.0 (ideal=60)
    # -> body 超过 ideal，触发 _split_section_body 切成 ["# A\n\nx x ...x",
    #    "# A\n\ny"] 两块，尾部是 "# A\n\ny" (5 tokens)
    document = MarkdownParser().parse(
        "# A\n\n" + "x " * 31 + "\n\ny",
        document_title="ratio.md",
    )

    # 情形 1：merge_below_ratio=0.625 -> 阈值=37；尾部 5 tokens < 37 -> 合并
    splitter_merges = RecursiveSplitter(
        tokenizer=CharacterTokenizer(),
        options=SplitOptions(
            max_tokens=60,
            ideal_max_tokens_ratio=1,
            merge_below_ratio=0.625,
            block_options=markdown_block_options(),
        ),
    )
    chunks_merges = splitter_merges.split(document)
    # 尾部 "y" 被合并进前一块；最终 1 个 chunk（前提是合并后 <= max_tokens=60）
    assert len(chunks_merges) == 1

    # 情形 2：merge_below_ratio=0.0 -> 禁用合并 -> 保留所有碎片
    splitter_keeps = RecursiveSplitter(
        tokenizer=CharacterTokenizer(),
        options=SplitOptions(
            max_tokens=60,
            ideal_max_tokens_ratio=1,
            merge_below_ratio=0.0,
            block_options=markdown_block_options(),
        ),
    )
    chunks_keeps = splitter_keeps.split(document)
    assert len(chunks_keeps) == 2
    assert chunks_keeps[1].body == "# A\n\ny"


def test_section_flat_registry_lookup() -> None:
    from lumberjack.core.splitters import (
        ExactSectionFlatSplitter,
        IncrementalSectionFlatSplitter,
        create_splitter,
    )

    assert create_splitter("section-flat").__class__ is ExactSectionFlatSplitter
    assert create_splitter("exact-section-flat").__class__ is ExactSectionFlatSplitter
    assert (
        create_splitter("incremental-section-flat").__class__
        is IncrementalSectionFlatSplitter
    )


def test_section_flat_does_not_subtree_collapse() -> None:
    """section-flat 永远不合并整棵子树，即使它很小。"""
    from lumberjack.core.splitters import ExactSectionFlatSplitter

    fixture = """# Parent

Parent intro.

## One

One body.

## Two

Two body.
"""
    document = MarkdownParser().parse(fixture, document_title="t.md")
    splitter = ExactSectionFlatSplitter(
        tokenizer=CharacterTokenizer(),
        options=SplitOptions(max_tokens=10000, merge_below_ratio=0.0),
    )

    chunks = splitter.split(document)

    # 即使整棵子树远小于预算，section-flat 也不做 subtree-collapse。
    assert len(chunks) == 3


def test_section_flat_does_not_merge_tail_fragments() -> None:
    """section-flat 不调用 _merge_small_chunks，尾部碎片保留。"""
    from lumberjack.core.splitters import ExactSectionFlatSplitter

    # 构造一个 body 超过 ideal_max_tokens 的 section，强制 _split_section_body
    # 切出多块；尾部碎片（小于 merge 阈值）在 section 模式下会被合并，
    # 在 section-flat 模式下保留。
    body = "x " * 200  # ~400 tokens
    document = MarkdownParser().parse(f"# A\n\n{body}", document_title="t.md")

    flat_splitter = ExactSectionFlatSplitter(
        tokenizer=CharacterTokenizer(),
        options=SplitOptions(
            max_tokens=100,
            ideal_max_tokens_ratio=0.5,
            merge_below_ratio=0.5,  # 阈值 = 50，flat 模式下不生效
            block_options=markdown_block_options(),
        ),
    )
    flat_chunks = flat_splitter.split(document)

    section_splitter = SectionSplitter(
        tokenizer=CharacterTokenizer(),
        options=SplitOptions(
            max_tokens=100,
            ideal_max_tokens_ratio=0.5,
            merge_below_ratio=0.5,
            block_options=markdown_block_options(),
        ),
    )
    section_chunks = section_splitter.split(document)

    # flat 模式产出的 chunk 数应 >= section 模式（因为 flat 不合并尾部）。
    # 由于 subtree-collapse 在这个 fixture 下会失败（body 远超 ideal_max_tokens=50），
    # section 会走 per-section + _merge_small_chunks；flat 只走 per-section。
    assert len(flat_chunks) >= len(section_chunks)
    # flat 至少切出 2 块（body 超过 ideal_max_tokens=50）
    assert len(flat_chunks) >= 2


def test_incremental_section_flat_does_not_subtree_collapse() -> None:
    """incremental-section-flat 同样不做 subtree-collapse 与尾部合并。"""
    from lumberjack.core.splitters import IncrementalSectionFlatSplitter

    fixture = """# Parent

Parent intro.

## One

One body.

## Two

Two body.
"""
    document = MarkdownParser().parse(fixture, document_title="t.md")
    splitter = IncrementalSectionFlatSplitter(
        tokenizer=CharacterTokenizer(),
        options=SplitOptions(max_tokens=10000, merge_below_ratio=0.0),
    )

    chunks = splitter.split(document)

    assert len(chunks) == 3
```

- [ ] **Step 2: 跑新测试**

Run:
```bash
cd /home/elery/pypj/lumberjack-private/.worktrees/merge-ratio-flat-section
uv run pytest tests/test_splitter.py -k "merge_below_ratio_threshold_derived or section_flat_registry or section_flat_does_not_subtree or section_flat_does_not_merge or incremental_section_flat_does_not_subtree" -v 2>&1 | tail -20
```

Expected: 全部 passed。如果 `test_merge_below_ratio_threshold_derived_from_max_tokens` 失败，检查 `_split_section_body` 实际切出的尾部 chunk 大小（用 `print` 或 `pytest --pdb` 调试），并调整 `merge_below_ratio` 使阈值明确大于/小于该尾部大小。

- [ ] **Step 3: 跑全量测试**

Run:
```bash
cd /home/elery/pypj/lumberjack-private/.worktrees/merge-ratio-flat-section
uv run pytest -q 2>&1 | tail -20
```

Expected: 全部 passed。

- [ ] **Step 4: type check + lint + format**

Run:
```bash
cd /home/elery/pypj/lumberjack-private/.worktrees/merge-ratio-flat-section
uv run ty check . 2>&1 | tail -20
uv run ruff check --fix 2>&1 | tail -20
uv run ruff format 2>&1 | tail -20
```

Expected: ty 无 error；ruff 无需 unsafe-fixes；format 完成。

- [ ] **Step 5: 提交所有源码 + 测试改动**

Run:
```bash
cd /home/elery/pypj/lumberjack-private/.worktrees/merge-ratio-flat-section
git add -A
git status
git commit -m "feat!: replace merge_below_tokens with merge_below_ratio and add section-flat splitters

BREAKING CHANGE:
- Remove SplitOptions.merge_below_tokens (absolute token count, default 50)
- Add SplitOptions.merge_below_ratio (fraction of max_tokens, default 0.125)
- ratio=0.0 disables merging (replaces None/negative)
- Remove SplitOptions.subtree_merge
- Add ExactSectionFlatSplitter / IncrementalSectionFlatSplitter
- New registry names: section-flat, exact-section-flat, incremental-section-flat
- section-flat variants disable subtree-collapse AND tail-fragment merging
- CLI: --merge-below-tokens -> --merge-below-ratio; new splitter choices
- Web API: merge_below_tokens -> merge_below_ratio in TextSplitRequest and Form"
```

Expected: 提交成功。

---

## Task 13: 文档 — README.md

**Files:**
- Modify: `README.md`

- [ ] **Step 1: 找出 README.md 中的引用**

Run:
```bash
cd /home/elery/pypj/lumberjack-private/.worktrees/merge-ratio-flat-section
grep -n "merge-below-tokens\|merge_below_tokens\|subtree_merge\|subtree-merge" README.md
```

- [ ] **Step 2: 更新 option 表格中的 `--merge-below-tokens` 行**

把 README.md 中 option 表格里的 `--merge-below-tokens` 行（约第 135 行 / 第 430 行附近）替换为：

```markdown
| `--merge-below-ratio` | Tail-fragment merge threshold as a fraction of `--max-tokens` in `[0.0, 1.0)`. Tail chunks below `int(max_tokens * ratio)` tokens are merged into their same-heading predecessor when the result fits `max_tokens`. `0` disables merging. Default `0.125`. |
```

（按实际表格列结构调整）

- [ ] **Step 3: 更新 splitter 表格，新增 flat 行**

在 splitter 表格（约第 490 行附近）的 `section` 行之后新增三行：

```markdown
| `section-flat` / `exact-section-flat` | Per-heading section splitter (no subtree-collapse, no tail-fragment merging) |
| `incremental-section-flat` | Same as `section-flat` with the additive incremental estimate path |
```

（按实际表格列结构调整；`section-flat` 和 `exact-section-flat` 是同一类的别名，可合并一行或分开——参照原 `section` / `exact-section` 的呈现方式）

- [ ] **Step 4: 更新示例命令**

把 README.md 中所有示例命令里的 `--merge-below-tokens 50` 替换为 `--merge-below-ratio 0.125`（或删除该 flag，因为 0.125 是默认值）。

- [ ] **Step 5: 移除 `subtree_merge` 提及**

把 README.md 中所有提及 `subtree_merge` 的地方删除或改写为「`section-flat` 变体」的描述。

---

## Task 14: 文档 — README.zh-CN.md

**Files:**
- Modify: `README.zh-CN.md`

- [ ] **Step 1: 同步 Task 13 的所有改动到中文版**

Run:
```bash
cd /home/elery/pypj/lumberjack-private/.worktrees/merge-ratio-flat-section
grep -n "merge-below-tokens\|merge_below_tokens\|subtree_merge\|subtree-merge" README.zh-CN.md
```

按 Task 13 的策略逐处更新中文版。option 表格的 `--merge-below-tokens` 行（约第 125 / 399 行）改为：

```markdown
| `--merge-below-ratio` | 尾部碎片合并阈值，`--max-tokens` 的比例，取值 `[0.0, 1.0)`。低于 `int(max_tokens * ratio)` tokens 的尾部 chunk 在合并后不超过 `max_tokens` 的前提下会被并入同标题前驱。`0` 禁用合并。默认 `0.125`。 |
```

splitter 表格新增 flat 行（中文描述）。示例命令同步更新。

---

## Task 15: 文档 — AGENTS.md

**Files:**
- Modify: `AGENTS.md`

- [ ] **Step 1: 找出 AGENTS.md 中的引用**

Run:
```bash
cd /home/elery/pypj/lumberjack-private/.worktrees/merge-ratio-flat-section
grep -n "merge_below_tokens\|subtree_merge\|merge-below-tokens\|subtree-merge" AGENTS.md
```

- [ ] **Step 2: 更新 `SectionSplitter` 描述**

把 AGENTS.md 中描述 `SectionSplitter` 的段落（约第 96 行）改写。原描述提到 `subtree_merge` 选项，改为：

```markdown
- `section.py` provides `SectionSplitter` (registry: "section"/"exact-section") and `SectionFlatSplitter` (registry: "section-flat"/"exact-section-flat"). `SectionSplitter` is subtree-first: collapses a fitting subtree into one chunk, otherwise one chunk per heading section. `SectionFlatSplitter` emits one chunk per heading section's direct body and recurses into children, with **no** subtree-collapse and **no** tail-fragment merging (regardless of `merge_below_ratio`). `IncrementalSectionSplitter`/`IncrementalSectionFlatSplitter` are the incremental-measure variants.
```

- [ ] **Step 3: 更新 CLI Behavior 段**

把 AGENTS.md 中 CLI 段（约第 179 行）提到的 `merge_below_tokens` / `subtree_merge` 改写为：

```markdown
- `merge_below_ratio` (CLI `--merge-below-ratio`, default `0.125`) controls tail-fragment merging as a fraction of `max_tokens`; `0` disables merging
- Splitter choices: `recursive` (default, = exact-recursive), `section` (default, = exact-section), `section-flat`, `exact-recursive`, `incremental-recursive`, `exact-section`, `incremental-section`, `exact-section-flat`, `incremental-section-flat`
```

- [ ] **Step 4: 更新 Splitting Rules 段**

把 AGENTS.md 中 "Splitting Rules" 段（约第 169 行）的 `subtree_merge` 描述删除，并更新 `merge_below_tokens` 描述为 `merge_below_ratio`。例如：

```markdown
- `SectionSplitter`: subtree-first — collapses a fitting subtree into one chunk, otherwise one chunk per heading section. `SectionFlatSplitter`: always per-heading, no subtree-collapse, no tail-fragment merging.
- Tail-fragment merging (`merge_below_ratio`, default `0.125`): bottom-up, merges same-heading adjacent `paragraph` chunks whose tail is below `int(max_tokens * ratio)` tokens, when the merged result fits `max_tokens`. Disabled when `ratio == 0`. `section-flat` variants disable this entirely.
```

- [ ] **Step 5: 更新 SplitOptions 字段说明**

把 AGENTS.md 中 `SplitOptions` 字段清单（约第 152 行）里的 `merge_below_tokens` / `subtree_merge` 行替换为：

```markdown
  - `merge_below_ratio: float = 0.125` — tail-fragment merge threshold as a fraction of `max_tokens`; `0` disables
```

并删除 `subtree_merge` 行。

---

## Task 16: 文档 — docs/recursive-splitter-merges.md

**Files:**
- Modify: `docs/recursive-splitter-merges.md`

- [ ] **Step 1: 找出引用**

Run:
```bash
cd /home/elery/pypj/lumberjack-private/.worktrees/merge-ratio-flat-section
grep -n "merge_below_tokens\|merge-below-tokens" docs/recursive-splitter-merges.md
```

- [ ] **Step 2: 把 `merge_below_tokens=15` 例子改为 ratio**

把 `docs/recursive-splitter-merges.md` 中 `max_tokens=50, merge_below_tokens=15` 的工作示例（约第 281–327 行）改为 `max_tokens=50, merge_below_ratio=0.3`（0.3*50=15，int=15 ✓）。算法描述中 "merge_below_tokens" 改为 "merge_below_ratio (× max_tokens)"。

---

## Task 17: 最终回归 + 提交文档

**Files:**
- 无文件改动

- [ ] **Step 1: 全量测试**

Run:
```bash
cd /home/elery/pypj/lumberjack-private/.worktrees/merge-ratio-flat-section
uv run pytest -q 2>&1 | tail -10
```

Expected: 全部 passed。

- [ ] **Step 2: type check + lint + format**

Run:
```bash
cd /home/elery/pypj/lumberjack-private/.worktrees/merge-ratio-flat-section
uv run ty check . 2>&1 | tail -10
uv run ruff check 2>&1 | tail -10
uv run ruff format 2>&1 | tail -10
```

Expected: 全绿。

- [ ] **Step 3: grep 全仓确认无残留**

Run:
```bash
cd /home/elery/pypj/lumberjack-private/.worktrees/merge-ratio-flat-section
grep -rn "merge_below_tokens\|subtree_merge\|merge-below-tokens\|subtree-merge" src/ tests/ 2>&1 | grep -v "\.pyc"
```

Expected: 无输出。

```bash
grep -rn "merge_below_tokens\|subtree_merge" README.md README.zh-CN.md AGENTS.md docs/recursive-splitter-merges.md 2>&1
```

Expected: 无输出（或仅在历史 spec `docs/superpowers/specs/2026-07-03-section-subtree-merge-option-design.md` 中出现，那个文件保留作历史记录）。

- [ ] **Step 4: 提交文档改动**

Run:
```bash
cd /home/elery/pypj/lumberjack-private/.worktrees/merge-ratio-flat-section
git add -A
git status
git commit -m "docs: update README/AGENTS for merge_below_ratio and section-flat splitters"
```

- [ ] **Step 5: 验证 worktree 干净**

Run:
```bash
cd /home/elery/pypj/lumberjack-private/.worktrees/merge-ratio-flat-section
git status
git log --oneline -5
```

Expected: working tree clean；最近 2 个 commit 是本次改动的 feat 与 docs commit（加上 Task 12 的合并提交，具体取决于 squash 策略）。

---

## 完成标准

- [ ] 全量 `uv run pytest` 通过
- [ ] `uv run ty check .` 无 error
- [ ] `uv run ruff check` 与 `ruff format` 干净
- [ ] `src/` 与 `tests/` 中无 `merge_below_tokens` / `subtree_merge` 残留
- [ ] `section-flat` / `exact-section-flat` / `incremental-section-flat` 三个新 registry 名通过 `create_splitter` 解析
- [ ] `merge_below_ratio` 默认 `0.125`、`0.0` 禁用、负值/`>=1` 抛错
- [ ] README、README.zh-CN、AGENTS.md、docs/recursive-splitter-merges.md 同步更新
