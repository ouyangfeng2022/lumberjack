# Lumberjack 文档

[English](../index.md)

Lumberjack 将 Markdown、HTML 和 DOCX 转换为适合检索的 Chunk，同时保留文档结构和标题上下文。先阅读[安装](getting-started/installation.md)，再通过[快速开始](getting-started/quickstart.md)完成第一次拆分。

## 什么样的 Chunk 适合检索？

Lumberjack 将 Chunk 正文与标题路径分开，保留来源信息，并在可配置的 token 预算下尊重文档块。一棵格式中立的 `DocTree` 支持所有内置 parser 格式和 splitter 策略。

| 我希望… | 从这里开始 |
| --- | --- |
| 选择策略或计量模式 | [拆分与计量](concepts/splitting.md) |
| 了解输出字段和来源位置 | [Chunk 与来源信息](concepts/chunks.md) |
| 配置代码块或表格行为 | [配置](guides/configuration.md) |
| 扩展流水线 | [自定义组件](guides/custom-components.md) |
| 调用 CLI 或 Web API | [参考](reference/cli.md) |

项目仍在建立 benchmark 套件；本站不会发布未经验证的性能或质量结论。
