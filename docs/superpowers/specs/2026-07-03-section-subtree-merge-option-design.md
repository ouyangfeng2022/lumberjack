# SectionSplitter: `subtree_merge` 选项

## 背景

`feat/section-subtree-merge` 已合并到 master：`SectionSplitter`（注册名 `section` / `exact-section` / `incremental-section`）增加了"子树优先合并"短路判定——整棵子树（含后代）在 `ideal_max_tokens` 预算内且无 standalone block 时合并为单 chunk；否则走原有 per-section 拆分。

用户反馈：旧策略（永远 per-section 拆开，永不合并整棵子树）需要保留，与新策略并存可选用。

## 目标

通过 `SplitOptions.subtree_merge` 布尔字段控制 `SectionSplitter` 的策略选择，**不新增注册名**：

- `subtree_merge=True`（默认）：当前 master 行为（子树优先合并）
- `subtree_merge=False`：旧的 per-section 行为（每个 section body 独立成 chunk，每 child 独立递归，**永不**做整棵子树合并）

## 非目标

- 不改 `RecursiveSplitter` 的任何行为
- 不新增注册名（`section` / `exact-section` / `incremental-section` 内部根据标志选择策略）
- 不改 CLI、web API、web UI（Python API 已足够；后续需要再加）
- 不改 tokenizer、parser、registry（`__init__.py`）

## 实现

### `src/lumberjack/core/models.py` — 新增字段

在 `SplitOptions` dataclass 加一个布尔字段：

```python
@dataclass(slots=True, frozen=True)
class SplitOptions:
    ...
    render_headings: bool = True
    subtree_merge: bool = True        # ← 新增
    block_options: dict[str, BaseParams] = field(default_factory=dict)
    ...
```

放在 `render_headings` 之后、`block_options` 之前（与其它行为类布尔标志聚在一起）。默认 `True` 保持当前 master 行为。无需在 `__post_init__` 做派生计算。

### `src/lumberjack/core/splitters/section.py` — 守卫短路

在两个类的 `_split_section` 的子树合并短路判定外层包一个 `if self.options.subtree_merge:` 守卫。`False` 时直接跳过短路判定，落到原有 per-section 逻辑（一字不改）。

`ExactSectionSplitter._split_section`：

```python
def _split_section(self, section: SectionNode) -> list[ChunkDraft]:
    if not (section.blocks or section.children or section.level > 0):
        return []

    if self.options.subtree_merge:                      # ← 新增守卫
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

    # ↓↓↓ 旧 per-section 逻辑（不变）↓↓↓
    chunks: list[ChunkDraft] = []
    standalone_kinds = self.options.standalone_kinds
    ...
```

`IncrementalSectionSplitter._split_section`：

```python
def _split_section(self, section: MeasuredSection) -> list[ChunkDraft]:
    node = section.node
    if not (node.blocks or section.children or node.level > 0):
        return []

    if self.options.subtree_merge:                      # ← 新增守卫
        if section.can_emit_as_single_chunk:
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

    # ↓↓↓ 旧 per-section 逻辑（不变）↓↓↓
    chunks: list[ChunkDraft] = []
    ...
```

注意：`ExactSectionSplitter` 的类 docstring 现在写的是"Subtree-first section splitter"——需要更新一句说明受 `subtree_merge` 控制。`IncrementalSectionSplitter` 同理。

### 不需要改的部分

- `base.py`、`exact.py`、`incremental.py`、`registry.py`（`__init__.py`）—— 注册名不变，helper 已存在
- `RecursiveSplitter` 两个类 —— 完全不动
- CLI、web、tokenizer、parser —— 完全不动

## 行为对照

文档（max_tokens=1000, ideal=800）：
```
# Parent          # body 100 tokens
  ## One          # body 100 tokens
  ## Two          # body 100 tokens
```
子树总 tokens 远小于 ideal：

| `subtree_merge` | 输出 |
|---|---|
| `True`（默认） | **1 个 chunk**（整棵子树合并） |
| `False` | **3 个 chunk**（Parent body / One / Two） |

含 standalone block 的子树：两种选项都走拆分路径（`subtree_merge=False` 时短路被跳过，直接走 per-section；body 含 standalone 触发 `_split_section_body`）。

## 测试

修改 `tests/test_splitter.py`：

### 新增对照测试（核心）

```python
def test_section_splitter_subtree_merge_option_controls_behavior() -> None:
    """subtree_merge=True collapses a fitting subtree; False keeps per-section."""
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
        options=SplitOptions(max_tokens=1000, merge_below_tokens=0, subtree_merge=True),
    ).split(document)
    assert len(merged) == 1
    assert merged[0].headings == ((1, "Parent"),)

    per_section = SectionSplitter(
        tokenizer=CharacterTokenizer(),
        options=SplitOptions(max_tokens=1000, merge_below_tokens=0, subtree_merge=False),
    ).split(document)
    assert [chunk.headings for chunk in per_section] == [
        ((1, "Parent"),),
        ((1, "Parent"), (2, "One")),
        ((1, "Parent"), (2, "Two")),
    ]
```

### 新增 incremental 对照

同样的 fixture，用 `IncrementalSectionSplitter` 跑 `subtree_merge=True` / `False`，断言同样差异（1 个 vs 3 个 chunk）。

### 新增默认值测试

```python
def test_split_options_subtree_merge_defaults_true() -> None:
    assert SplitOptions().subtree_merge is True
```

### 现有测试不受影响

之前 Task 4 改动的几个测试（`test_heading_splitter_merges_small_subtree_into_one_chunk` 等）默认 `subtree_merge=True`，行为不变，**不需要改**。

## 文档

- `AGENTS.md`：在 Splitting Rules 段补充 `subtree_merge` 选项说明
- `README.md` / `README.zh-CN.md`：在 SectionSplitter 描述行补充选项
- `models.py` 中 `SplitOptions` 的 docstring 补 `subtree_merge` 字段说明

## 验证命令

```bash
uv run ty check .
uv run ruff check --fix
uv run ruff format
uv run pytest tests/test_splitter.py
uv run pytest
```
