# SectionSplitter: 子树优先合并（all-or-nothing 拓扑）

## 背景

当前 `SectionSplitter`（注册名 `section` / `exact-section` / `incremental-section`）的拓扑是"永远 per-section 拆开"：每个 section 的直接 body 独立成一个 chunk，每个 child section 递归处理，最后再做一次 body 内文本回退小块合并。它**从不**合并不同的 section。

`RecursiveSplitter` 在子树无法整体放下时会进入 `_split_section_children`，把相邻的 body 和 child draft 尽量 pack 在一起——这增加了公共标题渲染的复杂度，budget 计算也更绕。

## 目标

给 `SectionSplitter` 加一层"子树优先合并成单 chunk"的短路判定：在递归进入子树前，先判断整棵子树（含所有后代）能否作为一个独立 chunk；若能则整棵子树输出为一个 chunk，否则走原有 per-section 拆分路径（**完全保留现有拆分逻辑与 body 内合并语义，不做任何跨 section 合并**）。

这样公共标题的计算与渲染更方便、budget 计算更简单，同时仍保留 SectionSplitter "不 pack 不同 section" 的清晰边界。

## 非目标

- 不修改 `RecursiveSplitter` 的任何行为。
- 不引入新的注册名（沿用 `section` / `exact-section` / `incremental-section`）。
- 不改 `_merge_small_chunks` 的语义（仍只合并 headings 相等的相邻 chunk，即同一 section body 拆出的 fragment/text_piece）。
- 不改 `SplitOptions`、tokenizer、parser、web/CLI 的对外接口。

## single-chunk 判定条件（与 `RecursiveSplitter` 完全一致）

一棵子树可以作为一个独立 chunk，当且仅当：

1. **整棵子树的渲染 token 总数 ≤ `ideal_max_tokens`**
2. **子树内不存在 standalone block**（即 `block_options` 里被标记为 `isolated=True` 的 block kind）：
   - section 自身的 body 没有 standalone block
   - 任何后代子树也没有 standalone block

只要这两个条件之一不满足，就拆分。

> 这与 `ExactRecursiveSplitter._split_section` 顶部的 `can_emit_as_single_chunk` + `_draft_budget_tokens(single) <= ideal_max_tokens` 判定完全等价。

## 算法

### 插入位置

在 `_split_section` **方法体最开头、所有现有逻辑之前**插入短路判定。现有的"空节点不输出 chunk"语义由短路下面的原有分支自然保留：

- exact 路径现有 `_split_section` 没有显式早退，靠 `if section.blocks or section.level > 0` 分支跳过空节点；短路判定插在方法开头后，对空 root（`blocks=[]`, `children=[]`, `level==0`）：`can_emit_as_single_chunk=True` 但 `entries=[]`（来自 `_entries_from_section`，对空 section 返回 `[]`），构造出的 draft body 为空，会在 finalize 的 `if not body: continue` 处被丢弃——与现状一致。
- incremental 路径现有 `_split_section` 第 105 行有显式早退 `if not (node.blocks or section.children or node.level > 0): return []`；短路判定插在它之后。

### exact 路径伪代码

```
def _split_section(section):  # section: SectionNode
    # === 新增短路 ===
    body_has_standalone  = any(b.kind in standalone_kinds for b in section.blocks)
    child_has_standalone = any(self._section_has_standalone(c) for c in section.children)
    if not body_has_standalone and not child_has_standalone:
        entries = self._entries_from_section(section)          # 递归收集整棵子树
        common  = common_heading_path(e.headings for e in entries)
        single  = self._draft_from_entries(entries, common, origin="section")
        if self._draft_budget_tokens(single) <= self.options.ideal_max_tokens:
            return [single]
    # === 短路结束 ===

    # ↓↓↓ 现有逻辑一字不改 ↓↓↓
    chunks = []
    if section.blocks or section.level > 0:
        # body 处理（含 standalone / oversized / body 内 _merge_small_chunks）
        ...
    for child in section.children:
        chunks.extend(self._split_section(child))
    return chunks
```

### incremental 路径伪代码

```
def _split_section(section):  # section: MeasuredSection
    node = section.node
    if not (node.blocks or section.children or node.level > 0):
        return []

    # === 新增短路 ===
    if section.can_emit_as_single_chunk:                      # 已在 _measure_section 缓存
        entries = self._entries_from_section(section)         # 递归收集整棵子树
        common  = common_heading_path(e.headings for e in entries)
        headings_token_count = self._heading_path_token_count(common)
        chunk_token_count    = self._heading_path_token_count(node.path[:-1]) + section.counts.subtree
        single = ChunkDraft(
            entries=entries,
            headings=common,
            headings_token_count=headings_token_count,
            body_token_count=chunk_token_count - headings_token_count,
            token_count=chunk_token_count,
        )
        if self._draft_budget_tokens(single) <= self.options.ideal_max_tokens:
            return [single]
    # === 短路结束 ===

    # ↓↓↓ 现有逻辑一字不改 ↓↓↓
    chunks = []
    if node.blocks or node.level > 0:
        ...
    for child in section.children:
        chunks.extend(self._split_section(child))
    return chunks
```

> incremental 路径的 `chunk_token_count` 计算与 `IncrementalRecursiveSplitter._split_section` 第 168-172 行完全一致：父标题（不含本节标题）+ 子树预算。`headings` 用 entries 真实 common prefix（而非 `node.path`）保证 finalize 重算无副作用——这也是 incremental recursive splitter 现有做法（第 178-184 行注释明确解释了原因）。

### 关键不变量

- **短路成功时**：返回的单 draft 必须覆盖整棵子树的所有 entry（所有 body + 所有后代 body），其 `headings` 是这些 entry 的真实 `common_heading_path`，使得 finalize 的重算无副作用。
- **短路失败时**：行为与现有 `SectionSplitter` 字符串相等——body 独立拆分（含 standalone / 文本回退 / body 内小块合并），每个 child 独立递归。
- **不做任何跨 section 合并**：两个不同 child 的输出、body 输出与 child 输出之间，永不合并（`_merge_small_chunks` 的头部条件已天然排除）。

## 实现方案

只改一个文件：`src/lumberjack/core/splitters/section.py`。

### `ExactSectionSplitter._split_section`

在方法开头插入短路判定，复用现有 helper：

- 子树 standalone 判定 → 复用 `ExactCountingMixin._section_has_standalone`（递归检查 blocks + 子树，已在 `exact.py:271` 存在）
- 子树 entries → 复用 `ExactCountingMixin._entries_from_section`（递归收集，已在 `exact.py:113` 存在）
- 子树 common headings → `common_heading_path(entry.headings for entry in entries)`
- 单 draft 构造 → 复用 `ExactCountingMixin._draft_from_entries`（已在 `exact.py:92` 存在，会自动重算 body/prefix token）
- budget 判定 → `self._draft_budget_tokens(single) <= self.options.ideal_max_tokens`

短路失败后，**保留现有的全部 body 处理与 child 递归代码不变**。

### `IncrementalSectionSplitter._split_section`

`MeasuredSection` 已经在 `_measure_section` 时预算好了所有需要的量，直接复用：

- 子树 standalone 判定 → `section.can_emit_as_single_chunk`（已缓存在 `MeasuredSection` 上）
- 子树 entries → 复用 `IncrementalCountingMixin._entries_from_section`
- 单 draft token count → `self._heading_path_token_count(node.path[:-1]) + section.counts.subtree`（参照 `IncrementalRecursiveSplitter._split_section` 第 168-184 行的构造方式：父标题不含本节标题，加上整棵子树预算）
- common headings → `common_heading_path(entry.headings for entry in entries)`
- budget 判定 → `self._draft_budget_tokens(single) <= self.options.ideal_max_tokens`

短路失败后，**保留现有的全部 body 处理与 child 递归代码不变**。

### 不需要改的部分

- `base.py`、`exact.py`、`incremental.py`、`registry.py`（`__init__.py`）—— 所有 helper 已经存在，注册名不变
- `RecursiveSplitter` 两个类 —— 完全不动
- 模型、tokenizer、parser、CLI、web —— 完全不动

## 行为差异样例

文档：
```
# A                # body 100 tokens
  ## A1            # body 100 tokens
  ## A2            # body 100 tokens
```
`max_tokens=1200, ideal=960`，A 子树总 tokens（含标题）= 900：

| | 旧 SectionSplitter | 新 SectionSplitter |
|---|---|---|
| 输出 | 3 个 chunk（A body、A1、A2） | **1 个 chunk**（整棵 A 子树） |

若 A 子树总 tokens = 1500（> 960），两者输出**完全相同**：3 个 chunk。

若 A 的 body 含一个 standalone 表格，无论子树大小都拆分（与 recursive 一致）。

## 测试计划

修改 `tests/test_splitter.py`：

### 需要更新的现有用例

逐个跑现有 section splitter 相关用例，凡是因为"现在子树会被合成单 chunk"而行为变化的，更新预期值。重点关注：
- `test_heading_splitter_keeps_sections_separate_without_repeating_children`
- `test_heading_splitter_splits_oversized_section_body`
- `test_heading_splitter_respects_empty_section_options`
- `test_splitter_recursively_descends_heading_levels_when_section_is_oversized`

### 新增用例

1. **`test_section_splitter_merges_subtree_when_within_budget`**（exact）
   - 构造一棵总 token ≤ `ideal_max_tokens` 的多级子树
   - 断言只输出 1 个 chunk，body 覆盖所有后代，headings 是 common prefix
2. **`test_section_splitter_falls_back_when_subtree_exceeds_budget`**（exact）
   - 子树总 token > `ideal_max_tokens`
   - 断言行为与旧 SectionSplitter 完全一致（body 独立 + 每 child 独立）
3. **`test_section_splitter_does_not_merge_when_subtree_has_standalone`**（exact）
   - 子树总 token ≤ `ideal_max_tokens`，但 body 含 standalone block
   - 断言走拆分路径
4. **`test_section_splitter_subtree_merge_does_not_cross_sibling_sections`**（exact）
   - 两个独立的顶级 section，各自能成单 chunk
   - 断言输出 2 个 chunk，**不合并成 1 个**
5. 对 incremental 变体复用同样的 4 个场景（用 `IncrementalSectionSplitter`）

### 验证命令

```bash
uv run ty check .
uv run ruff check --fix
uv run ruff format
uv run pytest tests/test_splitter.py
uv run pytest
```

## 风险与边界

- **破坏性变更**：直接替换 `section` 注册名的行为。AGENTS.md 明确允许破坏性变更。CLI/web 无需改代码（注册名不变）。
- **existing test 失败预期**：会有少量 section splitter 测试因行为变化而失败，按"行为变化"原则更新预期值，不人为构造旧行为。
- **subtree token 计算**：exact 路径每次预算都重算（与 recursive 一致，性能可接受）；incremental 路径直接读 `MeasuredSection.counts.subtree`，无额外开销。
