# Splitter 策略

Lumberjack 会先将 Markdown、HTML 或 DOCX 解析为统一的 `DocTree`，再按结构和
`max_tokens` 预算进行拆分。

| 策略 | 适用场景 |
| --- | --- |
| `sibling`（默认） | 希望 Chunk 尽量填满，并允许相邻同级小节共享上下文。 |
| `subtree` | 希望预算允许时完整保留一个章节及其子章节。 |
| `section` | 需要独立处理每个章节的直接正文。 |

## 计量模式

未加前缀的策略在规划时使用增量估算，最终仍会给出权威 token 计数。若每个拆分决策
都必须完整重计渲染文本，请使用 `exact-sibling`、`exact-subtree` 或
`exact-section`。显式的 `incremental-*` 名称与无前缀名称等价。

Tokenizer 与计量模式互不绑定，例如可以使用
`--tokenizer tiktoken --splitter incremental-sibling`。

## 上下文与预算

每个 Chunk 通过 `ancestor_headings` 和 `own_heading` 保留标题上下文。
`heading_sensitive` 只控制外部标题路径的 token 是否计入拆分预算，并不会移除返回的
标题元数据。

超长文本依次按段落、换行、句子、词语和硬切分回退。围栏代码块默认保持完整。
`sibling` 与 `subtree` 的 `merge_below_ratio` 默认值是 `0.125`：同一标题下过短的
文本尾段可在合并后仍满足预算时向前合并；设置为 `0` 可关闭。`section` 不会折叠子树，
也不会跨章节合并。
