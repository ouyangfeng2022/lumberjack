# 流水线与规范化渲染

[English](../../concepts/pipeline.md)

Lumberjack 将输入格式专属的解析与格式中立的拆分分开：

```text
Document -> Parser.parse() -> DocTree -> Splitter.split() -> ChunkDraft[]
         -> ChunkFinalizer.finalize() -> TextNormalizer -> TextTransformer -> Chunk[]
```

| 阶段 | 职责 |
| --- | --- |
| `Document` | 原始文本、bytes 或路径，加上格式和调用方提供的来源信息。 |
| `Parser` | 将 Markdown、HTML 或 DOCX 转换为 `DocTree`。 |
| `DocTree` | 由 `SectionNode` 构成的标题树及规范化 `DocumentBlock` 内容。 |
| `Splitter` | 选择拓扑，并在预算内产生未完成的 `ChunkDraft` 分组。 |
| `ChunkFinalizer` | 渲染 draft、执行后处理、重计 token，并创建 `Chunk`。 |

## 规范化渲染

`DocumentBlock.text` 是 splitter 使用的规范化渲染表示，并不一定是原始文本切片：Markdown 会被规范化，而 HTML 与 DOCX 会转换为相同的 Markdown-like 表示。因此所有 splitter 都能处理每种支持的输入格式。

`DocTree.source` 保留原始 Markdown 或 HTML 文本。二进制 parser 可以留空，或提供规范化文本表示。parser 能确定时会给出来源行号；DOCX 没有稳定的来源行号。

## 后处理阶段

默认 `TextNormalizer` 只稳定化换行符、BOM/NUL 字符和连续空行。默认 `TextTransformer` 保留 Markdown 表面语法。只有在检索流水线需要纯文本而非 Markdown-like 输出时，才使用 `PlainTextTransformer`。

如何替换某一个阶段且不绕过其他流水线步骤，请见[自定义组件指南](../guides/custom-components.md)。
