# SectionSplitter 子树优先合并 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 给 `SectionSplitter` 加一层"子树优先合并成单 chunk"短路判定：整棵子树（含后代）总 token ≤ `ideal_max_tokens` 且无 standalone block 时，整棵子树输出为一个 chunk；否则完全保留现有 per-section 拆分逻辑。

**Architecture:** 只改 `src/lumberjack/core/splitters/section.py` 一个文件，给 `ExactSectionSplitter._split_section` 和 `IncrementalSectionSplitter._split_section` 各在方法体开头插入一段短路判定，复用所有现有 helper（`_section_has_standalone`、`_entries_from_section`、`_draft_from_entries`、`MeasuredSection.can_emit_as_single_chunk`）。短路失败时 fallthrough 到现有逻辑，一字不改。

**Tech Stack:** Python 3.10+, pytest, hatchling。所有命令用 `uv run`。

**Worktree:** `/home/elery/pypj/lumberjack-section-subtree`（分支 `feat/section-subtree-merge`）

**Spec:** `docs/superpowers/specs/2026-07-03-section-subtree-merge-design.md`

---

## File Structure

- Modify: `src/lumberjack/core/splitters/section.py` — 给 `ExactSectionSplitter._split_section`（第 37-82 行）和 `IncrementalSectionSplitter._split_section`（第 97-137 行）开头各插入一段短路判定
- Modify: `tests/test_splitter.py` — 更新因行为变化而失败的现有用例；新增覆盖子树合并的用例
- 不动：`base.py`、`exact.py`、`incremental.py`、`registry.py`（`__init__.py`）、`models.py`、`RecursiveSplitter`、parser、tokenizer、CLI、web

---

## Task 1: 新增 exact 路径"子树优先合并"测试

**Files:**
- Test: `tests/test_splitter.py`（在文件末尾追加）

- [ ] **Step 1: 写第一个失败测试——子树在预算内时合并为单 chunk**

在 `tests/test_splitter.py` 末尾追加（注意：`SectionSplitter`、`MarkdownParser`、`CharacterTokenizer`、`SplitOptions`、`BaseParams`、`markdown_block_options` 已在文件顶部 import）：

```python
def test_section_splitter_merges_subtree_when_within_budget() -> None:
    """Subtree whose total rendered tokens <= ideal_max_tokens collapses to one chunk."""
    fixture = """# Parent

Parent intro.

## One

One body.

## Two

Two body.
"""
    document = MarkdownParser().parse(fixture, document_title="t.md")
    splitter = SectionSplitter(
        tokenizer=CharacterTokenizer(),
        options=SplitOptions(max_tokens=1000, merge_below_tokens=0),
    )

    chunks = splitter.split(document)

    assert len(chunks) == 1
    assert chunks[0].headings == ((1, "Parent"),)
    # Whole subtree rendered into one body
    assert "Parent intro." in chunks[0].body
    assert "## One" in chunks[0].body
    assert "One body." in chunks[0].body
    assert "## Two" in chunks[0].body
    assert "Two body." in chunks[0].body
```

- [ ] **Step 2: 运行测试，确认它失败（当前行为是 3 个 chunk）**

Run: `uv run pytest tests/test_splitter.py::test_section_splitter_merges_subtree_when_within_budget -v`

Expected: FAIL，`assert len(chunks) == 1` 报错显示实际是 3（Parent / One / Two）。

- [ ] **Step 3: 写第二个失败测试——子树含 standalone block 时不合并**

继续在 `tests/test_splitter.py` 末尾追加：

```python
def test_section_splitter_does_not_merge_when_subtree_has_standalone() -> None:
    """Standalone block in the subtree disables the single-chunk short-circuit."""
    fixture = """# Parent

| A | B |
|---|---|
| 1 | 2 |

## One

One body.
"""
    document = MarkdownParser().parse(fixture, document_title="t.md")
    splitter = SectionSplitter(
        tokenizer=CharacterTokenizer(),
        options=SplitOptions(
            max_tokens=10000,  # well above subtree size
            merge_below_tokens=0,
            block_options=markdown_block_options(
                {"table": BaseParams(isolated=True)},
            ),
        ),
    )

    chunks = splitter.split(document)

    # Standalone table forces split: not collapsed into one chunk.
    assert len(chunks) >= 2
    table_chunk = next(c for c in chunks if "| A |" in c.body)
    assert table_chunk.headings == ((1, "Parent"),)
```

> 注：表格块在 `MarkdownParser` 里的 block kind 是 `table`（已通过 `MarkdownParser().parse(...)` 实测确认；不要写成 `html_table`）。`markdown_block_options({"table": BaseParams(isolated=True)})` 把它标记为 standalone。

- [ ] **Step 4: 运行新测试，确认它们都失败**

Run: `uv run pytest tests/test_splitter.py::test_section_splitter_merges_subtree_when_within_budget tests/test_splitter.py::test_section_splitter_does_not_merge_when_subtree_has_standalone -v`

Expected: 第一个 FAIL（3 个 chunk 而非 1），第二个 PASS 或 FAIL（standalone 路径已被现有逻辑正确处理 —— 当前 SectionSplitter 遇到 body 含 standalone 会走 `_split_section_body`，所以这个测试可能已经通过；如果通过，说明 standalone 路径已经正确，留作回归保护）。

- [ ] **Step 5: 提交测试**

```bash
git add tests/test_splitter.py
git commit -m "test(section): add subtree-merge short-circuit tests for ExactSectionSplitter"
```

---

## Task 2: 实现 ExactSectionSplitter 子树优先合并短路

**Files:**
- Modify: `src/lumberjack/core/splitters/section.py:37-82`（`ExactSectionSplitter._split_section`）

- [ ] **Step 1: 阅读当前 `_split_section` 实现**

Run: `uv run python -c "import lumberjack.core.splitters.section as m; import inspect; print(inspect.getsource(m.ExactSectionSplitter._split_section))"`

确认当前方法体第 39-82 行结构（`chunks = []` 开头，先处理 body，再递归 children）。

- [ ] **Step 2: 在 `_split_section` 方法体最开头插入短路判定**

用 Edit 工具，把 `src/lumberjack/core/splitters/section.py` 中：

```python
    def _split_section(self, section: SectionNode) -> list[ChunkDraft]:
        """Return one direct-body draft per section, then recurse into children."""
        chunks: list[ChunkDraft] = []
        standalone_kinds = self.options.standalone_kinds
```

替换为（保留 `chunks: list[ChunkDraft] = []` 和 `standalone_kinds = self.options.standalone_kinds` 两行不动，只在其**之前**插入新代码）：

```python
    def _split_section(self, section: SectionNode) -> list[ChunkDraft]:
        """Return one direct-body draft per section, then recurse into children.

        Short-circuit: if the entire subtree (own body + all descendants) fits
        within ``ideal_max_tokens`` and contains no standalone block, collapse
        it into a single chunk.  Otherwise fall through to the per-section
        split path below (unchanged).
        """
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
```

> 注：`_section_has_standalone`（定义在 `exact.py:271`）、`_entries_from_section`（`exact.py:113`）、`_draft_from_entries`（`exact.py:92`）、`_draft_budget_tokens`（`exact.py:45`）均已存在。`common_heading_path` 已在文件顶部 `from ..models import ...` 里 —— **检查一下**：当前 `section.py` 第 3 行 `from ..models import ChunkDraft, Entry, HeadingPath, MeasuredSection, SectionNode` 并**没有** import `common_heading_path`，需要补。

- [ ] **Step 3: 补 `common_heading_path` 的 import**

Edit `src/lumberjack/core/splitters/section.py` 第 3 行：

```python
from ..models import ChunkDraft, Entry, HeadingPath, MeasuredSection, SectionNode
```

改为：

```python
from ..models import (
    ChunkDraft,
    Entry,
    HeadingPath,
    MeasuredSection,
    SectionNode,
    common_heading_path,
)
```

- [ ] **Step 4: 跑 Task 1 的两个测试，确认通过**

Run: `uv run pytest tests/test_splitter.py::test_section_splitter_merges_subtree_when_within_budget tests/test_splitter.py::test_section_splitter_does_not_merge_when_subtree_has_standalone -v`

Expected: 两个 PASS。

- [ ] **Step 5: 跑全套 splitter 测试，找出因行为变化而失败的现有用例**

Run: `uv run pytest tests/test_splitter.py -v`

Expected: 一些现有 section 用例失败（预期内，子树现在会被合并）。**逐个记录失败用例名**，留给 Task 4 处理。

- [ ] **Step 6: 类型检查与格式化**

Run: `uv run ty check src/lumberjack/core/splitters/section.py`
Run: `uv run ruff check --fix src/lumberjack/core/splitters/section.py`
Run: `uv run ruff format src/lumberjack/core/splitters/section.py`

Expected: ty 无错（warning 可忽略），ruff 无错。

- [ ] **Step 7: 提交**

```bash
git add src/lumberjack/core/splitters/section.py
git commit -m "feat(section): add subtree-merge short-circuit to ExactSectionSplitter"
```

---

## Task 3: 实现 IncrementalSectionSplitter 子树优先合并短路

**Files:**
- Modify: `src/lumberjack/core/splitters/section.py:97-137`（`IncrementalSectionSplitter._split_section`）

- [ ] **Step 1: 新增 incremental 路径的子树合并测试**

在 `tests/test_splitter.py` 末尾追加。先确认 import：需要 `IncrementalSectionSplitter`。检查文件顶部第 16-21 行，当前只 import 了 `IncrementalRecursiveSplitter, RecursiveSplitter, SectionSplitter, create_splitter`。补 `IncrementalSectionSplitter`：

```python
from lumberjack.core.splitters import (
    IncrementalRecursiveSplitter,
    IncrementalSectionSplitter,
    RecursiveSplitter,
    SectionSplitter,
    create_splitter,
)
```

然后在文件末尾追加：

```python
def test_incremental_section_splitter_merges_subtree_when_within_budget() -> None:
    """IncrementalSectionSplitter collapses a fitting subtree to one chunk."""
    fixture = """# Parent

Parent intro.

## One

One body.

## Two

Two body.
"""
    document = MarkdownParser().parse(fixture, document_title="t.md")
    splitter = IncrementalSectionSplitter(
        tokenizer=CharacterTokenizer(),
        options=SplitOptions(max_tokens=1000, merge_below_tokens=0),
    )

    chunks = splitter.split(document)

    assert len(chunks) == 1
    assert chunks[0].headings == ((1, "Parent"),)
    assert "Parent intro." in chunks[0].body
    assert "## One" in chunks[0].body
    assert "One body." in chunks[0].body
    assert "## Two" in chunks[0].body
    assert "Two body." in chunks[0].body
    # token_count is the authoritative full recount, estimated stays close.
    assert chunks[0].token_count > 0
    assert abs(chunks[0].token_count - chunks[0].estimated_token_count) <= 5
```

- [ ] **Step 2: 跑测试确认失败**

Run: `uv run pytest tests/test_splitter.py::test_incremental_section_splitter_merges_subtree_when_within_budget -v`

Expected: FAIL（当前 incremental 行为也是 3 个 chunk）。

- [ ] **Step 3: 给 `IncrementalSectionSplitter._split_section` 插入短路**

Edit `src/lumberjack/core/splitters/section.py`，把：

```python
    def _split_section(
        self,
        section: MeasuredSection,
    ) -> list[ChunkDraft]:
        """Return one direct-body draft per section, then recurse into children."""
        chunks: list[ChunkDraft] = []
        node = section.node
```

替换为（在早退判断之后插入短路；早退判断当前是 `if node.blocks or node.level > 0:` 分支，incremental 版没有显式早退 —— 复核一下当前结构）：

先 Read 当前 `IncrementalSectionSplitter._split_section`（第 97-137 行）确认结构，它**没有**显式早退 `if not (...): return []`，而是用 `if node.blocks or node.level > 0:` 包住 body 处理。所以短路插在 `node = section.node` 之后、`if node.blocks or node.level > 0:` 之前：

```python
    def _split_section(
        self,
        section: MeasuredSection,
    ) -> list[ChunkDraft]:
        """Return one direct-body draft per section, then recurse into children.

        Short-circuit: if the pre-measured subtree fits within
        ``ideal_max_tokens`` and ``can_emit_as_single_chunk`` is True, collapse
        it into a single chunk.  Otherwise fall through to the per-section
        split path below (unchanged).
        """
        chunks: list[ChunkDraft] = []
        node = section.node

        if section.can_emit_as_single_chunk and (
            node.blocks or section.children or node.level > 0
        ):
            entries = self._entries_from_section(section)
            common = common_heading_path(entry.headings for entry in entries)
            headings_token_count = self._heading_path_token_count(common)
            chunk_token_count = (
                self._heading_path_token_count(node.path[:-1])
                + section.counts.subtree
            )
            single = ChunkDraft(
                entries=entries,
                headings=common,
                headings_token_count=headings_token_count,
                body_token_count=chunk_token_count - headings_token_count,
                token_count=chunk_token_count,
                split_origin="section",
            )
            if self._draft_budget_tokens(single) <= self.options.ideal_max_tokens:
                return [single]
```

> 注：`node.path[:-1]` 的语义 —— 子树 budget `counts.subtree` 已经**含本节标题**（见 `incremental.py:174`），所以 prefix 用父标题（`node.path[:-1]`）加上 subtree，就得到完整的渲染 footprint。这与 `IncrementalRecursiveSplitter._split_section` 第 168-172 行的算法一致。`common_heading_path` 已在 Task 2 Step 3 import 过。

- [ ] **Step 4: 跑 incremental 测试确认通过**

Run: `uv run pytest tests/test_splitter.py::test_incremental_section_splitter_merges_subtree_when_within_budget -v`

Expected: PASS。

- [ ] **Step 5: 跑 incremental 版的 standalone 测试（沿用 exact 思路，可选但推荐）**

在 `tests/test_splitter.py` 末尾追加：

```python
def test_incremental_section_splitter_does_not_merge_when_subtree_has_standalone() -> None:
    """Standalone block disables the incremental single-chunk short-circuit."""
    fixture = """# Parent

| A | B |
|---|---|
| 1 | 2 |

## One

One body.
"""
    document = MarkdownParser().parse(fixture, document_title="t.md")
    splitter = IncrementalSectionSplitter(
        tokenizer=CharacterTokenizer(),
        options=SplitOptions(
            max_tokens=10000,
            merge_below_tokens=0,
            block_options=markdown_block_options(
                {"table": BaseParams(isolated=True)},
            ),
        ),
    )

    chunks = splitter.split(document)

    assert len(chunks) >= 2
```

Run: `uv run pytest tests/test_splitter.py::test_incremental_section_splitter_does_not_merge_when_subtree_has_standalone -v`

Expected: PASS。

- [ ] **Step 6: 类型检查与格式化**

Run: `uv run ty check src/lumberjack/core/splitters/section.py`
Run: `uv run ruff check --fix src/lumberjack/core/splitters/section.py`
Run: `uv run ruff format src/lumberjack/core/splitters/section.py`

Expected: 无错。

- [ ] **Step 7: 提交**

```bash
git add src/lumberjack/core/splitters/section.py tests/test_splitter.py
git commit -m "feat(section): add subtree-merge short-circuit to IncrementalSectionSplitter"
```

---

## Task 4: 更新因行为变化而失败的现有测试

**Files:**
- Modify: `tests/test_splitter.py`

- [ ] **Step 1: 跑完整 splitter 测试，列出全部失败用例**

Run: `uv run pytest tests/test_splitter.py -v 2>&1 | grep -E "FAIL|ERROR"`

记录每个失败用例的名字。

- [ ] **Step 2: 对每个失败用例，分析它是否因"子树现在合并"而失败**

对每个失败用例：

1. Read 该用例的 fixture 和断言。
2. 判断：它的 fixture 子树总 token 是否 ≤ `ideal_max_tokens` 且无 standalone block？
   - 是 → 行为变化是预期的（新策略正确合并），**更新断言**反映新行为（chunk 数变少、body 覆盖更多）。
   - 否 → 这是回归 bug，**不要**改测试，回到 Task 2/3 检查短路逻辑。

具体可疑用例（按 spec 列出，需逐个核实）：
- `test_heading_splitter_keeps_sections_separate_without_repeating_children`（第 178 行）—— fixture 是 `# Parent` + 两个 `##`，max_tokens=1000，**预期会合并成 1 个 chunk**。需要重写断言：从 3 个 chunk 改为 1 个，body 覆盖整个子树。
- `test_heading_splitter_splits_oversized_section_body`（第 201 行）—— fixture 是单 section body 超预算（max_tokens=35），子树超出预算，**短路失败**，行为应不变。
- `test_heading_splitter_splits_oversized_body_with_nosplit_blocks_kept_intact`（第 223 行）—— 同上，超预算，行为不变。
- `test_heading_splitter_respects_empty_section_options`（第 248 行）—— `# Empty` 无 body + `## Child`，子树很小，**预期合并成 1 个 chunk**（`skip_empty_sections=True` 时）。需要核实并更新。
- `test_create_splitter_routes_recursive_and_section`（第 164 行）—— 只检查类型，应不变。

- [ ] **Step 3: 更新 `test_heading_splitter_keeps_sections_separate_without_repeating_children`**

这个用例的目的是"section splitter 不重复渲染 child"，现在子树合并后仍是 1 个 chunk，child 内容在 body 里渲染一次。把它重写为反映新行为，并改名为更准确的描述：

把：
```python
def test_heading_splitter_keeps_sections_separate_without_repeating_children() -> None:
    document = MarkdownParser().parse(
        HEADING_SPLITTER_FIXTURE, document_title="heading.md"
    )
    splitter = SectionSplitter(
        tokenizer=CharacterTokenizer(),
        options=SplitOptions(max_tokens=1000, merge_below_tokens=0),
    )

    chunks = splitter.split(document)

    assert [chunk.headings for chunk in chunks] == [
        ((1, "Parent"),),
        ((1, "Parent"), (2, "One")),
        ((1, "Parent"), (2, "Two")),
    ]
    assert chunks[0].body == "# Parent\n\nParent intro."
    assert chunks[1].body == "# Parent\n\n## One\n\nOne body."
    assert chunks[2].body == "# Parent\n\n## Two\n\nTwo body."
    assert "One body." not in chunks[0].body
    assert "Two body." not in chunks[0].body
```

改为（保留"child 不重复渲染"的原意，但现在 child 在合并 chunk 里只出现一次）：

```python
def test_heading_splitter_merges_small_subtree_into_one_chunk() -> None:
    """A small subtree collapses into one chunk; children render once each."""
    document = MarkdownParser().parse(
        HEADING_SPLITTER_FIXTURE, document_title="heading.md"
    )
    splitter = SectionSplitter(
        tokenizer=CharacterTokenizer(),
        options=SplitOptions(max_tokens=1000, merge_below_tokens=0),
    )

    chunks = splitter.split(document)

    assert len(chunks) == 1
    assert chunks[0].headings == ((1, "Parent"),)
    # Common parent breadcrumb renders once; each child renders once.
    assert chunks[0].body.count("# Parent") == 1
    assert chunks[0].body.count("## One") == 1
    assert chunks[0].body.count("## Two") == 1
    assert "Parent intro." in chunks[0].body
    assert "One body." in chunks[0].body
    assert "Two body." in chunks[0].body
```

- [ ] **Step 4: 核实 `test_heading_splitter_respects_empty_section_options` 是否需要改**

Read 第 248-270 行后实测（已在计划编写阶段实测）：

- fixture `# Empty\n\n## Child\n\nChild body.`，max_tokens=1000
- `# Empty` 没有 body → `_entries_from_section(document.root)` 只产生一个 entry（`## Child` 的），其 headings 为 `((1, "Empty"), (2, "Child"))`
- 整棵子树 token 远小于 ideal_max_tokens，无 standalone → **短路成功**，合并成 **1 个 chunk**
- 这个 chunk 的 entries 是 `[((1, "Empty"), (2, "Child"))]`，common 是 `((1, "Empty"), (2, "Child"))`

所以 `default_chunks`（`skip_empty_sections=True`）的旧断言 `[chunk.headings == ((1, "Empty"), (2, "Child"))]` **不变**——只是 chunk 数从 1（原来 child 独立成 chunk）变为 1（合并后也是这一个 entry），实际行为对 `default_chunks` 来说**完全一致**。

但 `kept_chunks`（`skip_empty_sections=False`）旧行为是 2 个 chunk（`# Empty` 单独成空 chunk + `## Child`），新行为是 1 个 chunk（合并）。**这个需要更新**：

把：
```python
    assert [chunk.headings for chunk in default_chunks] == [
        ((1, "Empty"), (2, "Child")),
    ]
    assert [chunk.headings for chunk in kept_chunks] == [
        ((1, "Empty"),),
        ((1, "Empty"), (2, "Child")),
    ]
    assert kept_chunks[0].body == "# Empty"
```

改为：
```python
    # Both collapse the small subtree to a single chunk.
    assert [chunk.headings for chunk in default_chunks] == [
        ((1, "Empty"), (2, "Child")),
    ]
    assert [chunk.headings for chunk in kept_chunks] == [
        ((1, "Empty"), (2, "Child")),
    ]
    assert "# Empty" in kept_chunks[0].body
    assert "## Child" in kept_chunks[0].body
    assert "Child body." in kept_chunks[0].body
```

> 注：`# Empty` 的 body 在合并后没有独立 chunk —— 它的标题进入 chunk 的 heading 渲染。原断言 `kept_chunks[0].body == "# Empty"` 不再成立。

- [ ] **Step 5: 跑全套 splitter 测试，确认全部通过（或只剩已知 OK 的）**

Run: `uv run pytest tests/test_splitter.py -v`

Expected: 所有用例 PASS。如果还有失败，回到 Step 2 分析每个失败用例。

- [ ] **Step 6: 跑全量测试套件**

Run: `uv run pytest`

Expected: 全部 PASS。

- [ ] **Step 7: 类型检查 + lint + format（全工程）**

Run: `uv run ty check .`
Run: `uv run ruff check --fix`
Run: `uv run ruff format`

Expected: ty 无错，ruff 无错。

- [ ] **Step 8: 提交**

```bash
git add tests/test_splitter.py
git commit -m "test(section): update existing tests for subtree-merge behavior"
```

---

## Task 5: 补充跨同级兄弟不合并的回归测试

**Files:**
- Test: `tests/test_splitter.py`（末尾追加）

- [ ] **Step 1: 写两个独立顶级 section 各自合并、但不互相合并的测试**

在 `tests/test_splitter.py` 末尾追加：

```python
def test_section_splitter_subtree_merge_does_not_cross_top_level_sections() -> None:
    """Two top-level sections each collapse independently; not merged together."""
    fixture = """# First

First body.

# Second

Second body.
"""
    document = MarkdownParser().parse(fixture, document_title="t.md")
    splitter = SectionSplitter(
        tokenizer=CharacterTokenizer(),
        options=SplitOptions(max_tokens=1000, merge_below_tokens=0),
    )

    chunks = splitter.split(document)

    # Each top-level section collapses to its own chunk; they don't merge.
    assert len(chunks) == 2
    assert chunks[0].headings == ((1, "First"),)
    assert chunks[1].headings == ((1, "Second"),)
    assert "First body." in chunks[0].body
    assert "Second body." in chunks[1].body
    assert "Second body." not in chunks[0].body
```

- [ ] **Step 2: 跑测试确认通过**

Run: `uv run pytest tests/test_splitter.py::test_section_splitter_subtree_merge_does_not_cross_top_level_sections -v`

Expected: PASS。

> 为什么会通过：root（document root, level=0）的子树虽无 standalone，但子树总 token > ideal_max_tokens（两个 section + 它们的 body 合计），或者更精确地说，root 这层的短路检查会失败（因为整篇文档超过预算），然后 fallthrough 到 per-section，每个 `# First` / `# Second` 子树独立短路成功。如果 fixture 总 token 真的小于 ideal_max_tokens，那 root 短路会成功合并成 1 个 chunk —— **核实 max_tokens 设置**：`max_tokens=1000, ideal=800`，"First body." + "Second body." + 标题远小于 800，**root 短路会成功**。所以这个测试需要调整。

- [ ] **Step 3: 调整 fixture 让两个顶级 section 总和超过 ideal_max_tokens**

把 fixture 加长到总和 > 800（ideal），但各自仍 < 800：

```python
def test_section_splitter_subtree_merge_does_not_cross_top_level_sections() -> None:
    """Two top-level sections each collapse independently; not merged together."""
    # Each section body is ~150 chars; together they exceed ideal_max_tokens
    # (800) so the root short-circuit fails and each top-level section
    # collapses independently.
    first_body = "Alpha. " * 20  # ~140 chars
    second_body = "Bravo. " * 20  # ~140 chars
    fixture = f"""# First

{first_body}

# Second

{second_body}
"""
    document = MarkdownParser().parse(fixture, document_title="t.md")
    splitter = SectionSplitter(
        tokenizer=CharacterTokenizer(),
        options=SplitOptions(max_tokens=1000, merge_below_tokens=0),
    )

    chunks = splitter.split(document)

    # Root short-circuit fails (total > ideal); each top-level section
    # collapses to its own chunk.
    assert len(chunks) == 2
    assert chunks[0].headings == ((1, "First"),)
    assert chunks[1].headings == ((1, "Second"),)
    assert "Alpha." in chunks[0].body
    assert "Bravo." in chunks[1].body
    assert "Bravo." not in chunks[0].body
```

Run: `uv run pytest tests/test_splitter.py::test_section_splitter_subtree_merge_does_not_cross_top_level_sections -v`

Expected: PASS。如果失败显示是 1 个 chunk，说明 root 短路成功（总和仍 ≤ 800），把 `* 20` 加大到 `* 30` 或调小 `max_tokens`。

- [ ] **Step 4: 跑全量测试最终确认**

Run: `uv run pytest`
Run: `uv run ty check .`
Run: `uv run ruff check --fix`
Run: `uv run ruff format`

Expected: 全部 PASS，无 lint/类型错。

- [ ] **Step 5: 提交**

```bash
git add tests/test_splitter.py
git commit -m "test(section): add regression for cross-sibling non-merge"
```

---

## Task 6: 更新文档（AGENTS.md / README 如有提及 section splitter 行为）

**Files:**
- Possibly modify: `AGENTS.md`

- [ ] **Step 1: 搜索文档里描述 section splitter 行为的段落**

Run: `grep -rn "SectionSplitter\|section.*splitter\|one chunk per heading\|per-section" AGENTS.md README.md README.zh-CN.md 2>/dev/null`

- [ ] **Step 2: 更新 AGENTS.md 中"Splitting Rules"对 SectionSplitter 的描述**

`AGENTS.md` 里的 `## Splitting Rules` 段有一句：
> `SectionSplitter`: emits one chunk per heading section direct body; child sections become separate chunks

把这句改为：

> `SectionSplitter`: first attempts to collapse an entire subtree (own body + all descendants) into a single chunk when it fits `ideal_max_tokens` and has no standalone block; otherwise emits one chunk per heading section direct body and recurses into children (no cross-section merging).

同样更新同段里：
> `SectionSplitter`: emits one chunk per heading section direct body; child sections become separate chunks

找到 `## Architecture` 段对 section.py 的描述：
> `section.py` provides `SectionSplitter` (registry: "section") — one chunk per heading section

改为：
> `section.py` provides `SectionSplitter` (registry: "section") — subtree-first: collapses a fitting subtree into one chunk, otherwise one chunk per heading section

> CLI Behavior 段里有一句 "section (default, = exact-section)" 不需要改（注册名不变）。

- [ ] **Step 3: 核实 README 是否也有类似描述需要更新**

Run: `grep -n "one chunk per heading\|SectionSplitter" README.md README.zh-CN.md 2>/dev/null`

如果有，同步更新。

- [ ] **Step 4: 提交**

```bash
git add AGENTS.md README.md README.zh-CN.md
git commit -m "docs: describe SectionSplitter subtree-merge short-circuit"
```

---

## Definition of Done

- [ ] `uv run pytest` 全绿
- [ ] `uv run ty check .` 无错
- [ ] `uv run ruff check --fix` 无错
- [ ] `uv run ruff format` 无格式改动
- [ ] 新增测试覆盖：子树在预算内合并、含 standalone 不合并、跨同级不合并、incremental 路径同行为
- [ ] 现有测试已更新反映新行为
- [ ] `AGENTS.md` 已更新
- [ ] 所有提交在 `feat/section-subtree-merge` 分支上
