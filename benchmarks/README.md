# Benchmark MVP / 基准测试 MVP

This directory is a reproducible, versioned benchmark harness, not a runtime
dependency of `lumberjack-py`. It records the input corpus, configuration,
environment, every timed sample, and quality diagnostics.

此目录是可复现、受版本控制的 benchmark 工具，不是 `lumberjack-py` 的运行时依赖。
它记录语料、配置、环境、每次计时样本和质量诊断。

## Run / 运行

```bash
uv run python -m benchmarks.run --adapter lumberjack --splitter section
uv run python -m benchmarks.run --adapter lumberjack --splitter exact-section
```

Each command performs one warmup and five measured repetitions by default.
`raw.json` preserves samples and chunks; `summary.json` is a concise table
source. Results are written to `benchmarks/results/<date>-<commit>/` and are
ignored by Git so reports can be regenerated on the measured commit.

每条命令默认执行一次预热和五次测量。`raw.json` 保留样本与 chunk，`summary.json`
提供汇总表数据源。结果写入 `benchmarks/results/<date>-<commit>/`，并被 Git 忽略，
从而可在实际测量的提交上重新生成报告。

## Corpus / 语料

`datasets/manifest.json` is the dataset contract. Every document is CC0,
declares its scenario, required content, and protected content. The first
checked-in corpus provides one compact document per scenario; the corpus is
designed for deterministic harness validation, not for performance claims.

`datasets/manifest.json` 是数据集契约。每份文档均为 CC0，并声明场景、必需内容和
protected 内容。首批入库语料为每类场景提供一个紧凑文档，用来验证确定性基准工具，
不用于发布性能结论。

## Optional competitors / 可选竞品

Competitor adapters are never installed by the core package. The harness
supplies LangChain Recursive/Markdown, Unstructured basic/by-title, Docling
hierarchical, and Chonkie recursive adapters when their respective packages are
installed. Missing dependencies produce a clear skip/error instead of silently
changing the comparison.

竞品 adapter 不会被核心包安装。当前可使用 LangChain Recursive/Markdown、
Unstructured basic/by-title、Docling hierarchical 和 Chonkie recursive adapter。
依赖缺失会明确报错/跳过，绝不静默改变比较。
