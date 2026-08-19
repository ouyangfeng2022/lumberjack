# Chunk 与来源信息

[English](../../concepts/chunks.md)

`Chunk` 将用于检索的内容与章节上下文分成独立字段：

| 字段 | 含义 |
| --- | --- |
| `body` | 渲染后的 Chunk 正文。外部标题不会渲染在这里；内部合并章节的标题仍会保留在正文。 |
| `ancestor_headings` | 当前 Chunk 所属章节之上的标题路径。 |
| `own_heading` | 当前 Chunk 自身的 `(level, title)`，或多同级章节合并时的 `None`。 |
| `token_count` | 权威最终计数：标题、标题与正文之间的分隔符，以及后处理后的正文。 |
| `estimated_token_count` | split-time 估算；使用增量规划时可能与最终值略有不同。 |
| `headings_token_count` / `body_token_count` | 最终计数的两个组成部分。 |
| `start_line` / `end_line` | parser 能确定时的 1-based 来源位置。 |
| `document_title` / `document_path` | 源文档标识与来源信息。 |

标题路径采用规范化 Markdown 渲染。`heading_sensitive=True` 时，splitter 将渲染后的标题路径及正文前的空行分隔符计入预算；无论该设置为何，metadata 都会返回。

`SplitResult.document` 保留文档级 metadata 和 Markdown 引用定义。可用这些数据将入库的 Chunk 链接回来源，但不要假设 DOCX 等二进制输入一定有行号范围。
