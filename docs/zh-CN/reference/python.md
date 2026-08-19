# Python API 参考

[English](../../reference/python.md)

包根目录只导出 `Lumberjack` 与 `Document`；其他公开组件从其专属模块导入。

| 范围 | 公开入口 |
| --- | --- |
| 编排 | `lumberjack.Lumberjack`、`lumberjack.Document` |
| 模型 | `lumberjack.models`：`DocTree`、`DocumentBlock`、`SectionNode`、`ChunkDraft`、`Chunk`、`SplitResult` |
| 解析与拆分 | `lumberjack.parser`、`lumberjack.splitter` |
| 计量与 block 策略 | `lumberjack.tokenizer`、`lumberjack.block` |
| 最终处理 | `lumberjack.finalizer`、`lumberjack.normalizer`、`lumberjack.transformer` |
| 扩展契约 | `lumberjack.protocols` |

英文 API reference 从当前源码自动生成，包含完整签名和 docstring；上表提供等价的中文导航和术语说明。组件职责和可扩展方式分别见[流水线](../concepts/pipeline.md)与[自定义组件](../guides/custom-components.md)。
