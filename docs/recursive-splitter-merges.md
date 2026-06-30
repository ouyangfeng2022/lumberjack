# RecursiveSplitter 合并类型详解

本文档详细说明 `RecursiveSplitter` 在切分文档时的 **5 种合并类型**，每种合并的触发条件、
合并对象、合并后 chunk 的 **common headings（公共标题前缀）如何变化**，以及对应的 token 算术。

所有示例均来自实际运行的 splitter 输出（`SimpleCharTokenizer`，`token_count == len(body)`）。

---

## 背景知识

### 数据结构

切分过程使用三种中间结构（定义在 `src/lumberjack/core/splitters/drafts.py`）：

| 结构 | 含义 | 关键字段 |
| --- | --- | --- |
| `Entry` | 扁平化的内容单元（一个 section 的一段 body） | `headings`（该 entry 的**完整绝对标题路径**）、`body`、`body_token_count` |
| `ChunkDraft` | 一个 chunk 的草稿（一组 entry） | `headings`（chunk 级公共前缀）、`headings_token_count`、`body_token_count`、`token_count` |
| `MeasuredSection` | 带缓存的 SectionNode | `node.path`（从根到该节点的完整标题路径）、`counts`（title/body/subtree token 缓存） |

**关键点**：`SectionNode.path` 在解析时预计算（`parsers/markdown/parser.py` 的 `_build_section`），
形如 `((1, "Root"), (2, "Sub"), (3, "A"))`。获取任意节点的完整路径是 O(1)，无需向上遍历。

### 标题路径的两个层级

1. **`Entry.headings`** — entry 携带的**绝对完整路径**（创建时由 `node.path` 赋值）
2. **`ChunkDraft.headings`** — chunk 级的**公共前缀**（合并时派生，不是累积栈）

### token 算术的核心规则

项目通过"**末尾拼接使估算 == 实际**"实现精确估算，**不重新 tokenize 合并后的文本**：

- 每个内容单元按 `text + "\n\n"` 计数（带尾部分隔符），**最后一个单元除外**（不带）
- `join_markdown`（`utils.py`）是唯一的渲染原语：`"\n\n".join(parts)`
- 因此各单元 token 之和 == 渲染后整串的 token 数（对字符级 tokenizer 精确相等）
- tokenizer 的 text-string LRU cache 使重复计数廉价

### common headings 的结构性不变量

`common_heading_path`（`headings.py`）计算多个路径的**最长公共前缀**。但合并过程中，
5 种合并类型里有 4 种的 common 可以由结构性不变量直接得出，**无需重新计算**：

| 合并 | common 是否变化 | 能否省去重算 |
| --- | --- | --- |
| A. 整子树折叠 | 变（取 entries 真实公共前缀） | 一次性计算，后续不重算 |
| B. 相邻打包 | 恒为 `node.path` | ✅ 直接取，不调 `common_heading_path` |
| C. block 分片打包 | 不变（所有 entry 同 path） | ✅ 无需算 |
| D. 小 chunk 后处理合并 | 不变（合并条件要求 headings 相等） | ✅ 无需算 |
| E. finalize 渲染时重算 | 从所有 entries 重算 | 保留 `common_heading_path`（**唯一保留处**） |

---

## 合并类型 A：整子树折叠（Whole-subtree collapse）

**位置**：`recursive.py` `_split_section`，约 42-54 行

**触发条件**：当一个 section 的**整个子树**（自身 body + 所有后代）的 token 数
<= `ideal_max_tokens`，且 `can_emit_as_single_chunk` 为真时，整个子树**展平为一个 chunk**。

**合并对象**：parent 的 body entries + 所有后代 section 的 entries（通过 `_entries_from_section`
递归收集，每个后代 entry 携带该后代自己的 `node.path`）。

**common headings 变化**：

- 旧实现设为 `section.node.path`，但若 section 自身无 body 且子节点不对称，entries 的真实
  common 可能**比 `node.path` 更深**（见示例 A2）。
- 新实现修正为 **entries 的真实公共前缀**（`common_heading_path(entry.headings ...)`），
  保证 `draft.headings == entries 真实 common`，使 finalize 的重算变成纯验证。

**token 算术**：
```python
chunk_token_count = _heading_path_token_count(node.path[:-1]) + section.counts.subtree
```
- `node.path[:-1]`：祖先路径（这些标题作为 chunk-prefix 渲染）
- `section.counts.subtree`：自身标题 + body + 所有后代（已缓存）

### 示例 A1：子树整体装下 → 一个 chunk

输入：
```markdown
# Guide

## Intro

Hello world.

## Details

More detail.
```

`max_tokens=500`（子树 57 tokens，远小于预算）→ 整个 `# Guide` 子树折叠成 1 个 chunk：

```
[chunk 0] headings=((1, 'Guide'),)
          token=57  est=57
          body='# Guide\n\n## Intro\n\nHello world.\n\n## Details\n\nMore detail.'
```

**分析**：`# Guide` 的两个子节点 `## Intro`、`## Details` 都是 h2 且共享父路径 `((1,'Guide'))`，
所以 common = `((1,'Guide'))`。body 中 `# Guide` 作为公共前缀出现一次，`## Intro`、`## Details`
作为 internal-relative-headings 出现。

### 示例 A2：不对称子节点 → common 比 node.path 深

输入：
```markdown
# Root

## Sub

### A

alpha

### B

beta
```

`# Root` 无 body，子节点 `## Sub`；`## Sub` 又有子节点 `### A`、`### B`。整个子树装下：

```
[chunk 0] headings=((1, 'Root'), (2, 'Sub'))
          token=41  est=41
          body='# Root\n\n## Sub\n\n### A\n\nalpha\n\n### B\n\nbeta'
```

**分析**：entries 来自 `### A` 和 `### B`，它们的路径分别是 `((1,'Root'),(2,'Sub'),(3,'A'))`
和 `((1,'Root'),(2,'Sub'),(3,'B'))`。真实公共前缀是 `((1,'Root'),(2,'Sub'))`——
**比 `section.node.path`（即 `((1,'Root'))`）更深**。这就是为什么要用 entries 的真实 common，
而非 `node.path`。`# Root` 和 `## Sub` 都作为公共前缀各出现一次，`### A`、`### B` 作为
relative heading 出现。

---

## 合并类型 B：相邻打包（Adjacent packing / `add_packable`）

**位置**：`recursive.py` `_split_section_children` 中的 `add_packable` 闭包，约 90-109 行

**触发条件**：在 `_split_section_children` 中，将**父 section 的 body draft** 和**各子 section 的 draft**
作为平等的打包候选，逐个尝试塞入当前 `current_draft`，直到合并后超过 `ideal_max_tokens` 就 flush。

**合并对象**：父 body draft（headings=`node.path`）+ 相邻子 draft（headings 以 `node.path` 开头）。

**common headings 变化**：

- **恒为 `node.path`**（当前层的 section path）。这是结构性不变量：
  - 父 body draft 的 headings 就是 `node.path`
  - 子 draft 的 headings 是 `node.path + (child...)`，必然以 `node.path` 开头
  - 两者的最长公共前缀必然是 `node.path`
- 因此 `_merge_drafts` 调用时传入 `expected_common=node.path`，**省去 `common_heading_path` 重算**。

**token 算术**（`_merge_drafts`，加法 + separator delta 修正）：
```python
common_headings = expected_common  # = node.path，直接传入
headings_token_count = _heading_budget_token_count(common_headings)
left_body = left.token_count - headings_token_count   # 剥离已变 common 的 heading token
right_body = right.token_count - headings_token_count
body_token_count = left_body + right_body
# 若 left 最后一个 entry 有 body，加上 "\n\n" 分隔符的 token delta
token_count = headings_token_count + body_token_count
```

> **关键自洽性**：`left_body = left.token_count - new_common_tokens`。当 common 变浅时，
> 原 common 多出的 heading token（如 `## Child2` 相对于 `# Parent`）会**自动落入 body_token_count**，
> 这些 token 对应的标题会在 body 中作为 internal-relative-heading 渲染。

**budget 比较（render-aware）**：
```python
self._draft_budget_tokens(temp_merged_draft) > ideal_max_tokens  # 超过则 flush
```

### 示例 B1：父 body + 子节点打包到 ideal_max 为止

输入：
```markdown
# Parent

parent body line.

## Child1

c1 content.

## Child2

c2 content.

## Child3

c3 content.
```

`max_tokens=60`：

```
[chunk 0] headings=((1, 'Parent'),)
          token=51  est=51
          body='# Parent\n\nparent body line.\n\n## Child1\n\nc1 content.'
[chunk 1] headings=((1, 'Parent'),)
          token=56  est=56
          body='# Parent\n\n## Child2\n\nc2 content.\n\n## Child3\n\nc3 content.'
```

**分析**：
- `# Parent` 的 body（`parent body line.`）先打包，然后尝试加 `## Child1` → 51 tokens <= 60，打包成功
- 尝试再加 `## Child2` → 超过 60，flush chunk 0
- chunk 1 从 `## Child2` 开始，加 `## Child3` → 56 tokens <= 60，打包成功
- 两个 chunk 的 common 都是 `((1,'Parent'))`（符合不变量）
- chunk 1 中 `# Parent` 仍作为公共前缀出现，`## Child2`、`## Child3` 作为 relative heading

---

## 合并类型 C：block 分片打包（Block-fragment packing / `_split_section_body`）

**位置**：`base.py` `_split_section_body`，约 194-374 行

**触发条件**：当一个 section 自身的**块（block）内容**超过预算时（叶子节点或子节点都不适合折叠），
逐块累加进 `current_parts`，超过 body-only budget 就 flush 一个 chunk。

**合并对象**：同一个 section 内的**兄弟 block**（段落、代码块、表格等），它们**共享同一个 heading path**。

**common headings 变化**：**不变**。所有 entry 都用 `headings = node.path`，common 就是 `node.path`。

**token 算术**（加法 + separator delta 修正）：
```python
candidate_body_tokens = (
    current_body_tokens
    - count(current_parts[-1])                    # 旧最后一块无分隔符的计数
    + count(current_parts[-1] + SEPARATOR)        # 加上分隔符后的计数
    + block_tokens                                # 新块的计数
)
if candidate_body_tokens > budget:   # budget 是 body-only 预算
    flush_current()                   # 超预算则切出新 chunk
```

**budget 计算（render-aware）**：
```python
prefix_tokens = _heading_path_token_count(headings)   # full heading token（保留供 merge 算术）
if render_headings:
    body_budget = max_tokens - prefix_tokens           # 标题渲染，从预算扣除
else:
    body_budget = max_tokens                            # 标题不渲染，全额给 body
budget = body_budget
# 比较：candidate_body_tokens > budget
```

### 示例 C1：单 section 内多段落按预算切分

输入：
```markdown
# Section

paragraph 0: word word word word word

paragraph 1: word word word word word

...（共 6 段）
```

`max_tokens=45`（每段约 40 tokens，加标题超过 45）：

```
[chunk 0] headings=((1, 'Section'),)  token=49  body='# Section\n\nparagraph 0: word word word word word '
[chunk 1] headings=((1, 'Section'),)  token=49  body='# Section\n\nparagraph 1: word word word word word '
[chunk 2] headings=((1, 'Section'),)  token=49  body='# Section\n\nparagraph 2: word word word word word '
...（6 个 chunk，每段一个）
```

**分析**：每段单独成 chunk（单段 + 标题就接近预算）。所有 chunk 的 common 都是
`((1,'Section'))`，`# Section` 在每个 chunk 中作为公共前缀出现。

---

## 合并类型 D：小 chunk 自底向上后处理合并（`_merge_small_chunks`）

**位置**：`base.py` `_merge_small_chunks`，约 547-581 行

**触发条件**：在子树切分完成后（`recursive.py:60` 叶子 body 切分后、`recursive.py:172`
`_split_section_children` 返回前），对产生的 chunks 做一次**自底向上**的扫描，
把过小的尾部 chunk 合并到前一个相邻 chunk。仅在 `merge_below_tokens >= 0` 时启用。

**合并对象**：**严格相邻**的兄弟 chunk（`i-1` 和 `i`）。

**合并门控条件**（全部满足才能合并）：
```python
can_merge = (
    (parent_headings is None or previous.headings == parent_headings)  # 与父路径一致
    and previous.headings == current.headings                          # 两者 headings 相等
    and current.entries                                                # 非空
    and current.token_count < merge_below                              # 右侧 chunk 足够小
    and previous.chunk_type == "paragraph"                             # 类型为 paragraph
    and current.chunk_type == "paragraph"
)
# 合并后还不能超过 max_tokens（render-aware 比较）：
self._draft_budget_tokens(merged_draft) <= max_tokens
```

**扫描方向**：从右到左（`i` 从末尾递减到 1）。合并后左侧 slot 保留结果，循环继续，
因此一个左侧 chunk 可以**连续吸收多个右侧邻居**。

**common headings 变化**：**不变**。因为 `can_merge` 要求 `previous.headings == current.headings`，
公共前缀平凡地就是该共享路径。`_merge_drafts` 的 `common_heading_path` 计算会塌缩为相同路径。

> `chunk_type != "paragraph"`（如独立的代码块）会**故意阻止**此处的合并。

### 示例 D1：过小的尾部 chunk 被吸收

输入：5 段内容 + 一个极小的尾部 `final tiny.`

`max_tokens=50, merge_below_tokens=15`：

```
[chunk 0] headings=((1, 'Section'),)  token=35  body='# Section\n\np0: word word word word '
[chunk 1] headings=((1, 'Section'),)  token=35  body='# Section\n\np1: word word word word '
[chunk 2] headings=((1, 'Section'),)  token=35  body='# Section\n\np2: word word word word '
[chunk 3] headings=((1, 'Section'),)  token=35  body='# Section\n\np3: word word word word '
[chunk 4] headings=((1, 'Section'),)  token=48  body='# Section\n\np4: word word word word \n\nfinal tiny.'
```

**分析**：原本每段（约 35 tokens）单独成 chunk，`final tiny.`（约 11 tokens）也是一个小 chunk。
后处理扫描发现 `final tiny.` 小于 `merge_below_tokens=15`，且与前一个 chunk（`p4`）相邻、
同 headings、同类型 → 合并进 chunk 4（35 → 48 tokens，仍未超过 max_tokens=50）。
注意 p0-p3 没有互相合并，因为它们各自 35 tokens >= merge_below_tokens=15（门控要求**右侧** chunk 足够小）。

---

## 合并类型 E：finalize 渲染时重算（Final heading reconcile）

**位置**：`base.py` `_finalize_chunks`，约 389 行

**触发条件**：**每个**最终输出的 chunk 都会经过此步（不是 token 合并，而是渲染时的标题路径重整）。

**作用**：把 `ChunkDraft` 转成最终 `Chunk` 时，**从该 chunk 的所有 entries 重算 common headings**，
然后基于该 common 渲染 body。

```python
headings = common_heading_path(entry.headings for entry in chunk.entries)
body = self._render_body(chunk.entries, common_headings=headings)
```

**为什么需要**：Merge A 在 `recursive.py` 把 draft 的 headings 设成（修正后的）entries 真实 common，
但理论上 draft.headings 与 entries 重算结果应一致。finalize 重算是**权威来源**，
draft.headings 只是中间缓存。这一步确保最终 `Chunk.headings` 字段始终正确。

**body 渲染规则**（`_render_body`）：
1. 若 common 非空且 `render_headings=True`：渲染 common 作为前缀
2. 对每个 entry：计算 `relative_headings = entry.headings[len(common):]`（相对 common 的后缀），
   渲染这些 relative headings（**无论 render_headings 真假都渲染**，因为它们是 chunk 内部结构），
   再拼接 entry body
3. `join_markdown` 所有部分

### 示例 E1：不对称兄弟合并 → 公共前缀去重

输入（经典的 `MERGED_SECTION_FIXTURE`）：
```markdown
# Development Guide

## Current Scope

We are building.

## Milestones

### M0

First.

### M1

Second.

## Suggested Workflow

Follow these.
```

`max_tokens=500`（整体装下）→ 1 个 chunk：

```
[chunk 0] headings=((1, 'Development Guide'),)
          token=141  est=141
          body='# Development Guide\n\n## Current Scope\n\nWe are building.\n\n## Milestones\n\n### M0\n\nFirst.\n\n### M1\n\nSecond.\n\n## Suggested Workflow\n\nFollow these.'
```

**分析**：
- entries 来自 `## Current Scope`、`## Milestones`(含 `### M0`、`### M1`)、`## Suggested Workflow`
- 三者的共同前缀是 `((1,'Development Guide'))`——`##` 级标题各不相同
- 所以 `# Development Guide` 作为公共前缀在 body **只出现一次**（去重）
- 所有 `##`、`###` 标题作为 relative heading 出现在 body 中
- `chunk.headings == ((1,'Development Guide'))`，`section_level == 1`

---

## 5 种合并类型总览

| 类型 | 位置 | 合并对象 | common 变化 | 是否需要 `common_heading_path` |
| --- | --- | --- | --- | --- |
| **A. 整子树折叠** | `recursive.py:42-54` | parent body + 所有后代 → 1 chunk | 取 entries 真实 common（一次性，可能比 node.path 深） | 是（一次性计算） |
| **B. 相邻打包** | `recursive.py:90-109`（`add_packable`） | 父 body draft + 子 draft | 恒为 `node.path`（结构性不变量） | **否**（传 `expected_common=node.path`） |
| **C. block 分片打包** | `base.py:194-374` | 同一 section 的兄弟 block | 不变（所有 entry 同 path） | 否 |
| **D. 小 chunk 后处理** | `base.py:547-581` | 相邻同 parent 同 headings 的 chunk | 不变（合并条件要求相等） | 否（塌缩为相同路径） |
| **E. finalize 渲染重算** | `base.py:389` | 无（仅渲染） | 从所有 entries 重算 | **是（唯一保留处）** |

## render_headings 如何影响 5 种合并

`render_headings` **不改变合并的 common headings 计算逻辑**（common 由文档结构决定，与渲染无关），
它只在**两个对外接触点**生效：

| 接触点 | render_headings=True | render_headings=False |
| --- | --- | --- |
| **budget 比较**（B/D 的 flush 决策、C 的 body 切分） | 用 `token_count`（含 heading token） | 用 `body_token_count`（剥离 common heading token） |
| **finalize 的 estimated_token_count** | `= token_count`（full） | `= body_token_count`（剥离 common heading token） |

**draft 内部 token 算术始终保留 full heading tokens**（render-aware 只在对外接触点），
这是为了保证 `_merge_drafts` 的加法算术自洽——合并变浅时，原 common 多出的 heading token
自动落入 body_token_count，对应标题在 body 中作为 internal-relative-heading 渲染。

无论 `render_headings` 真假，都满足不变量：
```
estimated_token_count == token_count == tokenizer.count(body)
```
（即估算与实际渲染的 token 数精确相等）
