# 尾部碎片合并参数改比例 + section-flat splitter 拆分

## 背景

当前两处 API 设计与产品定位有冲突，需要做破坏性调整（项目处于开发期，允许破坏兼容）：

1. **尾部碎片合并阈值用绝对 token 数表示**：`SplitOptions.merge_below_tokens: int | None`（默认 `50`）。这个固定值在不同 `max_tokens` 下含义不稳定（`max_tokens=400` 时 50 是 12.5%，`max_tokens=4000` 时只有 1.25%），且需要用户每次调 `max_tokens` 时同步调整。改为 `max_tokens` 的比例更合理。同时产品决定**默认一定启用合并**（旧 API 用 `None`/负值显式禁用），让默认路径不需要额外参数。

2. **`SectionSplitter` 的 `subtree_merge` 是 `SplitOptions` 上的标志位**：`True`（默认）做整棵子树合并短路，`False` 走 per-section 拆分。但 `subtree_merge` 只对 `SectionSplitter` 有意义、对 `RecursiveSplitter` 完全无效，把它放在通用的 `SplitOptions` 上是泄漏了 splitter 专属语义到通用配置里。更合理的做法是**拆成不同的 splitter 注册名**——选择 splitter 本身就表达了策略选择。

## 目标

### A. `merge_below_tokens` → `merge_below_ratio`

- 移除 `SplitOptions.merge_below_tokens`（绝对值，默认 `50`，支持 `None`/负值禁用）
- 新增 `SplitOptions.merge_below_ratio: float`（默认 `0.125`，取值 `[0.0, 1.0)`）
- 内部阈值 = `max_tokens * merge_below_ratio`（例如 `max_tokens=1200, ratio=0.125` → 阈值 `150` tokens）
- `ratio = 0.0` 等价于禁用合并（替代旧的 `None`/负值语义，保留测试中 `=0`/`=-1` 表示禁用的习惯）
- **合并策略本身完全不变**：自底向上扫描，仅当两个相邻 chunk 满足「相同标题路径、双向 `paragraph` 类型、当前尾部 chunk 的预算 `< 阈值`」时尝试合并，合并后预算必须 `≤ max_tokens`，否则放弃
- 默认一定启用合并（默认 `ratio=0.125` ≠ 0）

### B. `subtree_merge` 从 `SplitOptions` 移除，拆分为不同 splitter

- 移除 `SplitOptions.subtree_merge`
- Splitter registry 调整：

  | 注册名                          | 类                              | subtree-collapse | 尾部碎片合并 |
  | ------------------------------ | ------------------------------ | :--------------: | :----------: |
  | `recursive` / `exact-recursive`| `ExactRecursiveSplitter`       |       N/A        |      ✅      |
  | `incremental-recursive`        | `IncrementalRecursiveSplitter` |       N/A        |      ✅      |
  | `section` / `exact-section`    | `ExactSectionSplitter`         |        ✅        |      ✅      |
  | `section-flat` / `exact-section-flat` | `ExactSectionFlatSplitter`（新） |   ❌    |     ❌       |
  | `incremental-section`          | `IncrementalSectionSplitter`   |        ✅        |      ✅      |
  | `incremental-section-flat`     | `IncrementalSectionFlatSplitter`（新） |   ❌  |      ❌      |

- `section-flat` 的语义：每个 heading section 的直接 body 独立成 chunk、递归子节点；**既不做** subtree-collapse 短路、**也不调用** `_merge_small_chunks`
- `recursive` 系列完全不受影响（没有 subtree 概念，合并行为照旧）

## 非目标

- **不改合并策略本身**（同标题、相邻、双向 paragraph、合并后不超 max_tokens）——只改参数表达方式
- **不改 React webui 前端**（`lumberjack_webui/`）——本次只改 Python 侧（库 + CLI + Web API）
- **不改 tokenizer、parser、visitor、block splitter**
- **不保留向后兼容**（开发期，允许破坏性变更）：`merge_below_tokens` 参数彻底移除，`subtree_merge` 字段彻底移除

## 实现

### `src/lumberjack/core/models.py` — `SplitOptions` 字段调整

```python
@dataclass(slots=True, frozen=True)
class SplitOptions:
    max_tokens: int = 1200
    ideal_max_tokens_ratio: float = 0.8
    merge_below_ratio: float = 0.125          # ← 替代 merge_below_tokens
    skip_empty_sections: bool = True
    render_headings: bool = True
    # subtree_merge 字段移除
    block_options: dict[str, BaseParams] = field(default_factory=dict)

    # derived
    ideal_max_tokens: int = field(init=False)
    standalone_kinds: frozenset[str] = field(init=False)

    def __post_init__(self):
        ...
        if not (0.0 <= self.merge_below_ratio < 1.0):
            raise ValueError(
                f"merge_below_ratio must be in [0.0, 1.0), got {self.merge_below_ratio}"
            )
        object.__setattr__(self, 'ideal_max_tokens',
                           max(1, int(self.max_tokens * self.ideal_max_tokens_ratio)))
        ...
```

**关键决策**：`merge_below_tokens` **不**作为 derived field 保留——彻底删除。消费方（`_merge_small_chunks`）改为现场计算 `int(self.options.max_tokens * self.options.merge_below_ratio)`。理由：用户明确要求彻底删除，避免「字段名带 tokens 但实际是派生值」造成的心智负担。

### `src/lumberjack/core/splitters/base.py` — 校验与合并函数

#### 校验（`_validate_options`）

替换原来的 `merge_below_tokens` 校验：

```python
if not (0.0 <= self.options.merge_below_ratio < 1.0):
    raise ValueError("merge_below_ratio must be in [0.0, 1.0)")
# 原来的 "merge_below_tokens must be smaller than max_tokens" 删除
```

#### `_merge_small_chunks`

```python
def _merge_small_chunks(self, chunks, *, parent_headings=None):
    """Merge adjacent same-parent chunks below the merge threshold, bottom-up."""
    merge_below = int(self.options.max_tokens * self.options.merge_below_ratio)
    if merge_below <= 0:          # ratio == 0 → 禁用
        return chunks
    if not chunks:
        return chunks

    merged = list(chunks)
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
            if self._draft_budget_tokens(merged_draft) <= self.options.max_tokens:
                merged[i - 1] = merged_draft
                del merged[i]
        i -= 1
    return merged
```

行为与原实现完全一致，仅阈值来源从 `self.options.merge_below_tokens` 改为现场按 ratio 计算。

### `src/lumberjack/core/splitters/section.py` — 拆出 flat 子类

引入两个新类。**flat 子类直接重写整个 `_split_section`**，不抽取共享方法——清晰优先于 DRY，因为 flat 与非 flat 的差异正好是「删掉 subtree-collapse 短路段 + 删掉 `_merge_small_chunks` 调用」，整体重写一次比过度抽象更易读。

#### `ExactSectionFlatSplitter`

```python
class ExactSectionFlatSplitter(BaseSectionMixin, ExactSplitter):
    """Section splitter 的 flat 变体：每个 heading section 独立成 chunk、递归子节点。

    与 ``ExactSectionSplitter`` 的差异：
    1. 不做 subtree-collapse 短路（整棵子树合并为单 chunk 的优化）
    2. 不调用 ``_merge_small_chunks``（尾部碎片合并在本变体下完全关闭）
    """

    def _split_section(self, section: SectionNode) -> list[ChunkDraft]:
        if not (section.blocks or section.children or section.level > 0):
            return []

        chunks: list[ChunkDraft] = []

        # section 自身的 body
        if section.blocks:
            body_chunks = self._split_section_body(section)
            chunks.extend(body_chunks)              # ← 不调用 _merge_small_chunks

        # 递归子节点
        for child in section.children:
            chunks.extend(self._split_section(child))

        return chunks
```

> 注：上面是简化示意。实际实现需保留原 `ExactSectionSplitter._split_section` 中 per-section 分支的所有细节（standalone block 处理、chunk_type 标注、empty section 过滤等），仅删掉 `if self.options.subtree_merge:` 守卫的整段短路、并把 `self._merge_small_chunks(body_chunks, ...)` 改成 `body_chunks`。

#### `IncrementalSectionFlatSplitter`

同理，重写 `IncrementalSectionSplitter._split_section`，删掉 `if self.options.subtree_merge and section.can_emit_as_single_chunk:` 守卫段、删掉 `_merge_small_chunks` 调用。

#### 别名

```python
SectionSplitter = ExactSectionSplitter                  # 保留
SectionFlatSplitter = ExactSectionFlatSplitter          # 新增
```

#### 现有 `ExactSectionSplitter` / `IncrementalSectionSplitter` 的清理

删除两个 `_split_section` 实现里的 `if self.options.subtree_merge:` 守卫——这两个类现在**永远**做 subtree-collapse（行为由类本身决定，不再由 option 控制）。

### `src/lumberjack/core/splitters/__init__.py` — Registry

```python
SPLITTER_REGISTRY: dict[str, type[BaseSplitter]] = {
    "recursive": ExactRecursiveSplitter,
    "exact-recursive": ExactRecursiveSplitter,
    "incremental-recursive": IncrementalRecursiveSplitter,
    "section": ExactSectionSplitter,
    "exact-section": ExactSectionSplitter,
    "section-flat": ExactSectionFlatSplitter,                # 新
    "exact-section-flat": ExactSectionFlatSplitter,          # 新
    "incremental-section": IncrementalSectionSplitter,
    "incremental-section-flat": IncrementalSectionFlatSplitter,  # 新
}
```

### `src/lumberjack/lumber.py` — 公共 API

```python
def lumber(
    ...
    merge_below_ratio: float = 0.125,        # ← 替代 merge_below_tokens: int | None = 50
    ...
):
    ...
    options = SplitOptions(
        max_tokens=max_tokens,
        ideal_max_tokens_ratio=ideal_max_tokens_ratio,
        merge_below_ratio=merge_below_ratio,   # ← 改
        skip_empty_sections=skip_empty_sections,
        render_headings=render_headings,
        block_options=resolved_block_options,
    )
```

### `src/lumberjack/cli.py` — CLI

```python
parser.add_argument(
    "--merge-below-ratio",
    type=float,
    default=0.125,
    help="Tail-fragment merge threshold as a fraction of max_tokens in [0.0, 1.0); "
         "0 disables merging (default: 0.125).",
)
```

`--merge-below-tokens` 参数完全移除。`args.merge_below_ratio` 透传给 `lumber()`。

`--splitter` 的 `choices` 增加 `section-flat`、`exact-section-flat`、`incremental-section-flat`。

### `src/lumberjack/web/routes.py` — Web API

```python
class TextSplitRequest(BaseModel):
    ...
    merge_below_ratio: float = 0.125          # ← 替代 merge_below_tokens: int | None = 50

# split_file 端点:
merge_below_ratio: float = Form(0.125),       # ← 替代 merge_below_tokens: int | None = Form(50)
```

已核对 `routes.py`：两个端点的 `splitter` 字段都是自由 `str` 透传给 `lumber()`，**没有**枚举校验，所以新增 splitter 名不需要改 `routes.py` 的 `splitter` 字段，只需改 `merge_below_tokens` → `merge_below_ratio`。

## 测试策略

### 更新现有测试

涉及 `merge_below_tokens` 的 7 个测试文件全部改写：

- `merge_below_tokens=0` / `=-1` / `=None` → `merge_below_ratio=0.0`
- `merge_below_tokens=N` → `merge_below_ratio=N / max_tokens`（在每个测试的 `max_tokens` 上下文中换算）
- 文件清单（按引用密度）：
  - `tests/test_splitter.py`（~30 处）
  - `tests/test_render_headings.py`（6 处，全部 `=0` → `ratio=0.0`）
  - `tests/test_api.py`（4 处，全部 `=-1` → `ratio=0.0`）
  - `tests/test_token_counting_modes.py`（2 处，`=10`）
  - `tests/test_html_table_integration.py`（2 处，`=-1`）
  - `tests/test_web.py`（2 处，`=-1`）
  - `tests/test_docx_parser.py`（1 处，`=20`）

涉及 `subtree_merge` 的测试（全部在 `tests/test_splitter.py`）：

- `test_split_options_subtree_merge_defaults_true` → **删除**（字段不存在了）
- `test_section_splitter_subtree_merge_option_controls_behavior` → 改写为对比 `section` vs `section-flat` 两个 splitter 的行为差异
- `test_incremental_section_splitter_subtree_merge_option_controls_behavior` → 同上，对比 `incremental-section` vs `incremental-section-flat`
- `test_section_splitter_subtree_merge_does_not_cross_top_level_sections` → 保留（验证 `section` 不跨顶层 section 合并），断言不变
- `test_subtree_merge_false_still_splits_standalone_blocks` → 改写为 `section-flat` 仍正确处理 standalone block

### 新增测试

- **`merge_below_ratio` 边界校验**
  - `< 0` 抛 `ValueError`
  - `>= 1` 抛 `ValueError`
  - `= 0.0` 不抛、且 `_merge_small_chunks` 直接 return（禁用）
  - `= 0.999` 合法
- **`merge_below_ratio` 与 `max_tokens` 的派生关系**
  - `max_tokens=1200, ratio=0.125` → 阈值 `150`
  - 通过一个构造的尾部碎片场景断言合并按 150 阈值触发/不触发
- **`section-flat` / `exact-section-flat` / `incremental-section-flat` 通过 `create_splitter` 解析**
  - registry lookup 成功
  - 返回正确的类
- **`section-flat` 行为**
  - 多层 heading 文档：每个 heading section（含子 section 的父 section 的直接 body）独立成 chunk
  - 不做 subtree-collapse：构造一个原本能被 `section` 合并为单 chunk 的小文档，断言 `section-flat` 产出 ≥2 个 chunk
  - 不做尾部碎片合并：构造一个会产生尾部碎片的场景，断言 `section-flat` 保留所有碎片、`section` 会合并
  - standalone block 仍被正确路由到独立 chunk（移植自 `test_subtree_merge_false_still_splits_standalone_blocks`）
- **`incremental-section-flat` 行为**
  - 与 `section-flat` 对应的 incremental 断言

### 回归

- 全量 `uv run pytest` 通过
- `uv run ty check .` 通过
- `uv run ruff check --fix && uv run ruff format` 通过

## 文档

- `README.md` / `README.zh-CN.md`
  - option 表格：`--merge-below-tokens` 行改为 `--merge-below-ratio`（默认 `0.125`，`0` 禁用）
  - splitter 表格：新增 `section-flat` / `exact-section-flat` / `incremental-section-flat` 三行
  - 示例命令更新
- `AGENTS.md`
  - `SplitOptions` 字段说明：`merge_below_tokens` → `merge_below_ratio`，删除 `subtree_merge`
  - `SectionSplitter` 描述：拆分为 `section`（含 subtree-collapse + 合并）和 `section-flat`（都不做）
  - CLI 行为、Web API 行为段同步更新
  - "Splitting Rules" 段更新
- `docs/recursive-splitter-merges.md`
  - 把 `max_tokens=50, merge_below_tokens=15` 的例子改为 `max_tokens=50, merge_below_ratio=0.3`（15/50）
  - 算法描述中 "merge_below_tokens" 改为 "merge_below_ratio (× max_tokens)"
- 旧 spec `docs/superpowers/specs/2026-07-03-section-subtree-merge-option-design.md` 不删（历史记录），本 spec 在背景段已说明它被取代

## 实施顺序

1. **worktree 准备**：在 `.worktrees/` 下创建 `merge-ratio-flat-section` 分支与工作树，跑一遍 baseline 测试确认干净
2. **`SplitOptions` 改字段 + 校验**（`models.py` 删 `merge_below_tokens` 加 `merge_below_ratio` 删 `subtree_merge`、`base.py::_validate_options` 同步改）
3. **`_merge_small_chunks` 改读 ratio**（`base.py`）
4. **section.py 同步重构**（单次原子改动，避免中间状态 type error）：
   - 新增 `ExactSectionFlatSplitter` / `IncrementalSectionFlatSplitter` 两个类，重写 `_split_section`（无 subtree-collapse、无 `_merge_small_chunks`）
   - 清理 `ExactSectionSplitter` / `IncrementalSectionSplitter` 的 `_split_section` 中 `if self.options.subtree_merge:` 守卫（守卫读取的字段已在第 2 步删除，必须与本步骤同步）
   - 更新别名（`SectionFlatSplitter`）
5. **registry 更新**（`__init__.py`）
6. **公共 API + CLI + Web API**（`lumber.py`、`cli.py`、`web/routes.py`）
7. **更新测试**（7 个测试文件 + `subtree_merge` 相关测试改写）
8. **新增测试**（ratio 边界、flat 行为）
9. **文档**（README、AGENTS.md、recursive-splitter-merges.md）
10. **回归验证**：`ty check`、`ruff`、全量 `pytest`

> 注：第 2、3、4、5、6 步在同一个 commit 里完成最安全（互相依赖，分开 commit 中间状态无法通过 type check）。第 7、8 步测试更新也要在同一次「代码改动 → 测试更新 → 通过」的循环里，避免 `pytest` 在中途红。

## 风险与决策记录

| 决策点 | 选择 | 理由 |
| ------ | ---- | ---- |
| `merge_below_tokens` 是否作为 derived field 保留 | **彻底删除** | 用户明确要求；避免「字段名带 tokens 实际是派生值」的心智负担 |
| flat 子类是否抽取共享方法 | **直接重写 `_split_section`** | 清晰优先于 DRY；flat 与非 flat 差异正好是「删两段代码」，重写更易读 |
| `ratio=0` 语义 | **等于禁用合并** | 保留测试中 `merge_below_tokens=0/-1` 表示禁用的习惯 |
| 是否保留向后兼容 | **不保留** | 项目处于开发期，AGENTS.md 明确允许破坏性变更 |
| 是否同步改 webui | **本次不改** | 用户决策，仅改 Python 侧 |
