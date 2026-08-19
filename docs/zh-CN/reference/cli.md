# CLI 参考

[English](../../reference/cli.md)

`lumber` 读取一个 Markdown、HTML 或 DOCX 文件，并向标准输出写入一个 JSON 对象。使用 `--output` 可将 JSON 写到文件。

```bash
lumber INPUT [OPTIONS]
```

| 参数 | 默认值 | 含义 |
| --- | --- | --- |
| `--input-format` | `auto` | `auto`、`markdown`、`html` 或 `docx`；自动模式按扩展名判断。 |
| `--tokenizer` | `approx` | `approx`、`tiktoken` 或 `transformers`；只负责编码和 token 计数。 |
| `--splitter` | `section` | 文档拓扑与计量模式，见[拆分与计量](../concepts/splitting.md)。 |
| `--max-tokens` | `1200` | 每个 Chunk 的最大 token 数。 |
| `--ideal-max-tokens-ratio` | `0.8` | 首选拆分预算与 `max_tokens` 的比值。 |
| `--merge-below-ratio` | `0.125` | `[0.0, 1.0)` 内的同标题尾段合并阈值；`0` 表示关闭。 |
| `--[no-]heading-sensitive` | 启用 | 是否将外部标题路径 token 计入预算；标题 metadata 始终返回。 |
| `--max-heading-level` | 未设置 | 保留为章节上下文的最大标题层级。 |
| `--block-config` | 可重复 | 单个 block 策略：`KIND[:isolated][:nosplit][:TOKENS]`。 |
| `--block-config-json` | 未设置 | 结构化 JSON 策略，会覆盖同 kind 的 `--block-config` 值。 |
| `-o`、`--output` | stdout | 输出文件路径。 |

示例：

```bash
lumber handbook.md \
  --max-tokens 800 \
  --tokenizer tiktoken \
  --splitter incremental-sibling \
  --block-config table:500:nosplit:isolated
```

执行 `lumber --help` 可查看自动生成的帮助文本。文档构建与 CLI 契约测试确保这里的公开参数与当前实现同步。
