# Benchmark 方法论

Lumberjack 不会在没有可链接、可重复报告的情况下发布性能或质量结论。benchmark MVP
针对公开 CC0 语料记录结构质量、token 预算准确性和性能样本。

在仓库根目录运行：

```bash
uv run python -m benchmarks.run --adapter lumberjack --splitter section
```

默认每份文档执行一次预热和五次测量，结果写入
`benchmarks/results/<date>-<commit>/` 下的 `raw.json` 与 `summary.json`。
`raw.json` 包含完整配置、提交、Python/平台信息、每个计时样本和 chunk；报告不能以
单次运行作为依据。

## 指标

| 指标 | 含义 |
| --- | --- |
| `content_recall` | 在输出 chunk 中找到的数据集必需内容比例。 |
| `duplication_rate` | 非有意重复的重复 chunk payload 占全部 chunk 的比例。 |
| `budget_violation_rate` | 超过 `max_tokens` 的非 protected chunk；超长 protected block 不计入。 |
| `block_break_rate` | 没有恰好出现在一个 chunk 中的 protected 数据集 block 比例。 |
| `chunk_utilization` | 非 protected chunk 的已使用预算。 |
| `estimate_error` | 估算 token 数与最终 token 数之间的平均相对误差。 |
| `provenance_coverage` | 同时携带起止源行号的 chunk 比例。 |
| `token_p50` / `token_p95` | 输出 chunk 的 token 数分布。 |

性能测量包括墙钟时间、CPU 时间、Python 分配峰值、每 MB 吞吐量，以及 tokenizer
`count`/`encode` 调用次数。报告保存 median、P95、标准差和每个原始样本。

## 可比性

每个 adapter 必须在生成的报告中记录等价配置。如果工具无法保持标题、protected block
或 provenance，这属于明确写出的不可比项，而不是被隐藏的缺失值。竞品包只是可选的
benchmark 依赖，绝不会成为核心包依赖。

入库语料刻意保持很小，用于验证工具本身。仅可在讨论的同一提交上运行扩展且版本化的
语料并在此链接确切结果目录后，才可发布结论。
