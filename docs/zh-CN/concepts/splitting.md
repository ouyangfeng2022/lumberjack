# 拆分与计量

[English](../../concepts/splitting.md)

每个 splitter 都消费同一个 `DocTree`，但会在应用 token 预算前选择不同的文档拓扑。

| Splitter | 拓扑 |
| --- | --- |
| `SiblingSplitter` / `sibling` | 打包能放下的相邻同级章节，并保留它们的共享上下文。 |
| `SubtreeSplitter` / `subtree` | 预算允许时保留完整章节子树；无法容纳时才在章节内部回退。 |
| `SectionSplitter` / `section` | 独立处理每个章节的直接正文；不会折叠子树。这是默认策略。 |

## 精确与增量规划

无前缀的类和集成名称使用增量计量：它们在决定是否打包内容时维护一个加法估算，随后由 `ChunkFinalizer` 完成权威的最终计数。显式 `incremental-*` 集成名称与之等价。

`ExactSiblingSplitter`、`ExactSubtreeSplitter` 和 `ExactSectionSplitter` 会在规划时完整重计每个渲染候选项。当规划精度比速度更重要时，使用对应的 `exact-*` CLI 和 Web API 名称。

这与 tokenizer 引擎无关。`approx` 从 UTF-8 字节长度估算 token；`tiktoken` 和 `transformers` 需要 `tokenizers` extra。任何 tokenizer 都能配合任一种计量模式。

## 预算控制

- `max_tokens` 是最大目标预算。
- `ideal_max_tokens_ratio`（默认 `0.8`）是决定切分位置时使用的首选预算，必须大于零且不超过一。
- `merge_below_ratio`（默认 `0.125`）会在合并结果仍能容纳时，把同标题下较短的文本尾段合入前一个 Chunk。设为 `0` 可关闭。它作用于 sibling/subtree splitter，不会跨 section 正文合并。
- `heading_sensitive=True`（默认）会把外部标题路径 token 计入拆分预算，但不会从返回 metadata 中移除标题。
- `max_heading_level` 限制保留为章节上下文的标题深度；更深的标题会渲染到正文中。

## 超长 block 与表格

超长文本按以下顺序回退：段落分隔、换行、句子、词语，最后硬切分。围栏代码块默认保持完整，除非 block 策略允许拆分。受保护 URL 片段或显式不可拆分的 block 因此可能超过 `max_tokens`。

Markdown 和 HTML 表格可以在每个拆分片段重复表头。类型安全的表格策略见[配置](../guides/configuration.md)。
