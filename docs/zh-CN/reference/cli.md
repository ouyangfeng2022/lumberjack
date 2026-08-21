# CLI 参考

[English](../../reference/cli.md)

`lumber` 读取一个已支持的文档文件，并向标准输出写入带版本的 JSON 对象。使用
`--output` 可将 JSON 写到文件。目录或 glob 会按输入顺序处理并输出 JSONL；每个输入都会有成功或失败记录，进度和错误始终写入 stderr。

```bash
lumber INPUT [OPTIONS]
```

| 参数 | 默认值 | 含义 |
| --- | --- | --- |
| `--input-format` | `auto` | 所有文档列出的输入格式，包括 `sql`、`sqlite`、`notebook`，以及 `python`、`javascript`、`typescript`、`bash`、`c`、`cpp`、`csharp`、`go`、`java`、`kotlin`、`lua`、`php`、`ruby`、`rust`、`swift`、`zig` 等代码格式；自动模式按支持的扩展名判断。语法感知代码解析需要 `code-parsing`。 |
| `--tokenizer` | `approx` | `approx`、`tiktoken` 或 `transformers`；只负责编码和 token 计数。 |
| `--splitter` | `section` | 文档拓扑与计量模式；LOG、CSV/TSV、JSON/JSONL、XML 和 YAML 请使用 `record`，以保持输入记录的原子性，见[拆分与计量](../concepts/splitting.md)。 |
| `--max-tokens` | `1200` | 每个 Chunk 的最大 token 数。 |
| `--ideal-max-tokens-ratio` | `0.8` | 首选拆分预算与 `max_tokens` 的比值。 |
| `--merge-below-ratio` | `0.125` | `[0.0, 1.0)` 内的同标题尾段合并阈值；`0` 表示关闭。 |
| `--[no-]heading-sensitive` | 启用 | 是否将外部标题路径 token 计入预算；标题 metadata 始终返回。 |
| `--max-heading-level` | 未设置 | 保留为章节上下文的最大标题层级。 |
| `--block.<kind>.isolated` | 未设置 | 设置一种 block 是否必须单独成块：`true` 或 `false`。 |
| `--block.<kind>.split` | 未设置 | 设置超预算 block 是否可拆分：`true` 或 `false`。 |
| `--block.<kind>.max-tokens` | 未设置 | 设置该 kind 的正整数 token 预算。 |
| `--block.table.repeat-header`、`--block.html_table.repeat-header` | 未设置 | 设置拆分 Markdown 或 HTML 表格时是否重复表头：`true` 或 `false`。 |
| `-o`、`--output` | stdout | 输出文件路径。 |
| `--output-dir` | 未设置 | 为每个输入写一个 JSON 记录；已有文件必须显式传入 `--overwrite`。 |
| `--recursive` | 禁用 | 输入为目录时递归处理。 |
| `--jsonl` | 禁用 | 单个输入也输出 JSONL。 |
| `--fail-fast` | 禁用 | 首个输入失败时停止。 |

`<kind>` 可取 `paragraph`、`blockquote`、`list`、`list_item`、`table`、
`html_table`、`code_block`、`code_fence`、`html_block`、`front_matter`、
`math_block` 或 `math_block_eqno`。同一选项可重复使用，最后一个值生效。

示例：

```bash
# 单个文档。
lumber handbook.md \
  --max-tokens 800 \
  --tokenizer tiktoken \
  --splitter incremental-sibling \
  --block.table.max-tokens 500 \
  --block.table.split false \
  --block.table.isolated true

# 安全地将目录流入后续处理管道。
lumber data/ --recursive | jq -c 'select(.status == "success")'

# 为每个输入保留结果，不会意外覆盖既有输出。
lumber 'data/**/*.md' --recursive --output-dir chunks/
```

执行 `lumber --help` 可查看自动生成的帮助文本。文档构建与 CLI 契约测试确保这里的公开参数与当前实现同步。
