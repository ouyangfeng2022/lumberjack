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

## Parser corpus benchmark / Parser 大语料基准

The parser benchmark is separate from splitter comparison. It measures the
direct `Document -> Parser.parse() -> DocTree` boundary over version-pinned
external corpora, so chunking cannot hide parser failures. Sources are declared
in `datasets/parser_sources.json`; downloaded data stays under the ignored
`datasets/external/` directory.

Parser benchmark 与 splitter 对比分离，直接测量
`Document -> Parser.parse() -> DocTree`，避免 chunking 掩盖解析失败。外部语料及
固定版本声明在 `datasets/parser_sources.json` 中；下载内容保存在被忽略的
`datasets/external/` 目录。

```bash
# Fetch all pinned corpora. Use --source ID to fetch a subset.
uv run python -m benchmarks.fetch_parser_corpora

# Deterministically sample up to 500 documents from every source.
uv run python -m benchmarks.parser_run \
  --seed 20260824 \
  --sample-size-per-source 500

# Use every eligible document from selected sources.
uv run python -m benchmarks.parser_run \
  --source commonmark-0.31.2 \
  --source python-docx-tests \
  --sample-size-per-source 0
```

The pinned set combines a project-owned Markdown element conformance suite, 652
normative CommonMark cases, real Kubernetes documentation, python-docx
interoperability fixtures, LibreOffice Writer OOXML regression documents, the
html5lib tree-construction adversarial HTML fragments, and the MDN Learning
Area real-world HTML pages. Random selection is stratified per source and is
stable for the same seed. Every selected document records its corpus-relative
path, SHA-256, byte size, status, exception, timings, Python allocation peak,
lexical-token and non-whitespace-character recall, element assertions, and tree
statistics. `raw.json` preserves all document evidence, including dirty-worktree
status; `summary.json` reports aggregate, per-format, and per-dataset results.

固定语料包括项目自有的 Markdown 元素一致性套件、652 个 CommonMark 规范样例、
真实 Kubernetes 文档、python-docx 互操作 fixture、LibreOffice Writer OOXML
回归文档、html5lib tree-construction 对抗性 HTML 片段，以及 MDN Learning Area
真实 HTML 页面。随机抽样按来源分层，并在相同 seed 下保持稳定。每份样本记录相对
路径、SHA-256、大小、状态、异常、耗时、Python 内存分配峰值、词法 token
recall、非空白字符 recall、元素断言和树结构统计；`raw.json` 保留逐文档证据，
`summary.json` 提供总体、按格式和按数据集汇总。

## Random corpus benchmark / 随机语料基准

`random_run.py` verifies every parser beyond Markdown and DOCX (HTML, text,
logs, CSV/TSV, JSON/JSONL/YAML/TOML/XML, XLSX, SQLite, Python/JS/TS, notebooks,
SQL) against seeded document generators. Each generated document carries three
oracles: the visible text the generator emitted (token/character recall),
exact element-signature counts, and — for adversarially damaged payloads — the
exact exception types a clean rejection may raise. Results use the same
report format as the pinned-corpus benchmark.

`random_run.py` 用种子化生成器验证 Markdown 和 DOCX 之外的每一个解析器
（HTML、文本、日志、CSV/TSV、JSON/JSONL/YAML/TOML/XML、XLSX、SQLite、
Python/JS/TS、notebook、SQL）。每份生成文档携带三个 oracle：生成时记录的
可见文本（token/字符 recall）、精确的元素签名计数，以及对对抗性损坏载荷
允许的干净拒绝异常类型。结果与固定语料基准使用同一报告格式。

```bash
# All 18 formats, 500 documents each, deterministic for a given seed.
uv run python -m benchmarks.random_run \
  --seed 20260825 \
  --documents-per-format 500

# A quick subset run.
uv run python -m benchmarks.random_run \
  --formats html,csv,json,xlsx \
  --documents-per-format 50
```

Token recall is sensitive to producer-specific DOCX run boundaries, so it is
not an element-correctness score. Character recall checks retention despite run
fragmentation, while the local conformance cases explicitly assert required and
forbidden element kinds. See the parser coverage reference in the documentation
for the supported syntax matrix and known limitations.

## Optional competitors / 可选竞品

Competitor adapters are never installed by the core package. The harness
supplies LangChain Recursive/Markdown, Unstructured basic/by-title, Docling
hierarchical, and Chonkie recursive adapters when their respective packages are
installed. Missing dependencies produce a clear skip/error instead of silently
changing the comparison.

竞品 adapter 不会被核心包安装。当前可使用 LangChain Recursive/Markdown、
Unstructured basic/by-title、Docling hierarchical 和 Chonkie recursive adapter。
依赖缺失会明确报错/跳过，绝不静默改变比较。
