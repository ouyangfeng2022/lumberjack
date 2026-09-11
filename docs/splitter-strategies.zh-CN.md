# Splitter 策略

[English](splitter-strategies.md)

Lumberjack 会先将 Markdown、HTML 或 DOCX 解析为统一的 `DocTree`，再按结构和
`max_tokens` 预算进行拆分，并提供面向平面输入的 record 拆分器。本页是决策指南：
对每个选项说明何时使用、输出长什么样、代价是什么。这些决策的完整可运行版本见
`examples/technical_document.py`、`examples/table_chunking.py` 与
`examples/incremental_counting.py`。

## 选择拓扑

| 策略 | 适用场景 | 代价 |
| --- | --- | --- |
| `section`（默认） | 每个标题下的正文必须独立成立——API 参考、FAQ、法律文本。 | Chunk 预算填充率较低；不跨章节合并。 |
| `sibling` | 希望产出少而饱满的 Chunk，允许相邻同级小节共用一个 Chunk。 | 一个 Chunk 可能横跨两个同级小节；按小节定位粒度变粗。 |
| `subtree` | 短小的嵌套小节应整体保留——一个 `##` 下有许多小 `###` 的教程。 | 子树能塞进预算时会整体成一个 Chunk，最深层小节失去独立入口。 |
| `record` | 没有真实层级的平面输入——CSV/TSV、JSONL、日志。 | 完全没有标题上下文；完整记录永不拆分。 |

### `section`——每个标题一个正文

```text
输入:                        输出 Chunk:
# Guide                      "# Guide / Intro + 首段"
## Intro                     "# Guide / Config + 正文"
## Config                    "# Guide / Advanced + 正文"
### Advanced
```

当下游按标题检索或过滤、且混入相邻章节会造成干扰时使用。代价：某章节用掉预算的
90% 后，剩余 10% 会被闲置，因为下一章节总是另起新 Chunk。

### `sibling`——打包相邻同级小节

```text
输入:                        输出 Chunk:
# Guide                      "# Guide / Intro + Config（合并后占预算 95%）"
## Intro (30 tok)            "# Guide / Advanced + 正文"
## Config (60 tok)
### Advanced
```

适合偏好更少、更饱满 Chunk 的 RAG 管道。代价：检索到的 Chunk 可能带有相邻小节的
文本；并且 `merge_below_ratio` 此时可以跨同级边界生效（见下文）。

### `subtree`——保留完整分支

```text
输入:                        输出 Chunk:
# Guide                      "# Guide / Config 子树（### Advanced 一并纳入）"
## Config                    "# Guide / Usage 子树"
### Advanced
## Usage
```

当父标题离开子标题就没有意义时使用（例如 `## Configuration` 的各个 `###` 都很短）。
代价：只要装得下，整条分支会折叠成一个 Chunk，`###` 小节不再单独成检索单元。

### `record`——没有标题的输入

```text
输入: CSV/JSONL/日志          输出 Chunk:
row,row,row                  完整记录打包至 max_tokens
```

平面格式不应套用层级拆分器：键会变成伪标题，同级合并会虚构出不存在的结构。请使用
`record`（CLI 和 Web API 会按 `--input-format csv`/`jsonl`/`log` 自动选择）。单条
记录超过预算时会完整输出并标记 `protected`，而不是被静默拆开。

## 选择计量模式

| 模式 | 名称 | 拆分决策 | 适用场景 |
| --- | --- | --- | --- |
| 增量 | 无前缀与 `incremental-*` | 运行中的累加估算 | 大语料、热路径——tokenizer 调用大幅减少 |
| 精确 | `exact-*` | 对每个候选完整重计 | 预算紧张、需要计费级 token 核算 |

两种模式给出的 `token_count` 完全一致：最终权威计数始终由 finalizer 完成。差异只在
拆分器如何规划：

- **增量**预先测量一次文档树，此后维护运行估算。拆分时会存在小的相对误差
  （可在 Web UI 和 `Chunk.estimated_token_count` 中看到），`approx` tokenizer 下
  中英混合文本通常只有几个百分点。
- **精确**对每个候选重计一次，拆分决策与最终计数完全一致——代价是每次决策一次
  tokenizer 调用。

Tokenizer 与计量模式互不绑定：`--tokenizer tiktoken --splitter
incremental-sibling` 合法，`--tokenizer approx --splitter exact-section` 同样合法。
`examples/incremental_counting.py` 会用 tokenizer 调用次数、耗时和估算误差实测两种
模式。

## 调节预算参数

### `ideal_max_tokens_ratio`（默认 `0.8`）

拆分器以 `int(max_tokens * ratio)` 为拆分目标，为最终追加的标题上下文留出余量。
当文档标题路径很深、或使用 `approx` tokenizer 需要防低估的安全边际时调低（例如
`0.6`）；正文朴素、Chunk 明显填充不足时向 `1.0` 调高。

### `merge_below_ratio`（默认 `0.125`，`0` 关闭）

拆分后，同一标题下小于 `int(max_tokens * ratio)` tokens 的文本尾段会在合并结果仍
满足预算时并入邻居。当 Chunk 边界必须可预测、可 diff 复现时设为 `0`——此时即使
只有 3 个 token 的段落也会独立成 Chunk。注意 `section` 拆分器只在单章节直接正文内
合并，因此 `0` 主要影响 `sibling` 与 `subtree` 拓扑。

### `heading_sensitive`（默认 `true`）

控制外部标题路径是否计入拆分预算。当标题路径极长（深层嵌套文档）且希望正文用满
预算时设为 `false`——规划时标题 token 近乎免费。它只改变预算计算：Chunk 依然返回
`ancestor_headings`、`own_heading` 和相同的最终 `token_count`（始终包含标题路径），
检索元数据不会消失。

## 超长块与受保护块

超长围栏代码依次按段落、换行、句子、词语和硬切分回退——但显式配置为不可拆分的块
保持完整：

```python
from lumberjack.block import BlockConfig, BlockKind

# 代码围栏即使超出 max_tokens 也保持完整
block_options=[BlockConfig(kind=BlockKind.CODE_FENCE, split=False)]
```

这样的块会整体输出为一个标记 `protected=True` 且超过 `max_tokens` 的 Chunk。当“代码
示例被切碎”比“Chunk 超预算”更糟时（教程、API 文档），这是正确的取舍。应把
`protected` 视作下游处理的信号而非预算违规：benchmark 质量指标对它是单独核算的。

## 速查表

| 场景 | 配置 |
| --- | --- |
| 有层级文档的默认选择 | `section` |
| 面向向量检索的饱满 Chunk | `sibling`，`merge_below_ratio` 保持默认 |
| 短小嵌套小节应整体保留 | `subtree` |
| CSV / JSONL / 日志 | `record` |
| 严格、可复现的边界 | 任一拓扑 + `exact-*`，`merge_below_ratio=0` |
| 超大语料 | `incremental-*`（或无前缀）+ `approx` |
| 计费级核算 | `exact-*` + `tiktoken` |
