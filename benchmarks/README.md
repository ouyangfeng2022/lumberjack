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
declares its scenario, required content, and protected content. The checked-in
corpus provides five documents per scenario (technical, tables, code/formula,
short sections, long paragraphs, mixed language) plus three cross-format
equivalence groups, each pair shipping the same visible content as Markdown
and HTML under a shared `group` id. DOCX equivalence is covered by the parser
benchmarks because the splitter harness reads textual sources. The corpus is
designed for deterministic harness validation and repeatable comparison, not
for performance marketing.

`datasets/manifest.json` 是数据集契约。每份文档均为 CC0，并声明场景、必需内容和
protected 内容。入库语料为每类场景（技术文档、表格、代码/公式、大量短 section、
超长段落、中英混合）各提供五份文档，另附三组跨格式等价文档：每组以相同可见内容
分别提供 Markdown 和 HTML 版本，共享同一个 `group` id。DOCX 等价性由 parser
基准覆盖，因为 splitter 基准工具只读取文本语料。该语料用于验证确定性基准工具
和可重复对比，不用于性能营销。

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

## Random splitter benchmark / 随机 splitter 基准

`splitter_random_run.py` measures the six hierarchical splitter variants
(section/subtree/sibling topology × exact/incremental counting) under identical
tokenizers and documents: split-phase wall/CPU speed, tokenizer `count` call
volume, the gap between the split-time estimate
(`Chunk.estimated_token_count`) and the finalizer's authoritative recount
(`Chunk.token_count`), final chunks exceeding `max_tokens`, content-fidelity
oracles, and cold-run tracemalloc allocation peaks. Parsing runs once per
document outside every timed region; every variant splits the same `DocTree`.

`splitter_random_run.py` 在相同 tokenizer 与文档下测量六个 hierarchical
splitter 变体（section/subtree/sibling 拓扑 × exact/incremental 计数）：
split 阶段 wall/CPU 速度、tokenizer `count` 调用量、split 期估计值
（`Chunk.estimated_token_count`）与 finalizer 权威重计数（`Chunk.token_count`）
的误差、最终 chunk 超出 `max_tokens` 的情况、内容保真 oracle，以及 tracemalloc
冷启动分配峰值。每份文档只解析一次且不计入计时；所有变体切分同一棵 `DocTree`。

Timing and memory are measured in separate passes: timed repetitions run without
tracemalloc so wall times are clean, and the tokenizer text cache is cleared
before every repetition so each timed split starts from a zero cache — the
production semantics, since text caches are request-local and never reused
across documents. Warmup runs only load the tokenizer backend into memory and
reach interpreter/allocator steady state; they never warm the timed cache.
Memory is measured with fresh tokenizer caches per repetition
(`--memory-reps`, cold-run peaks for split alone and for split + finalize).
Per-document results report both the median and the mean over `--repetitions`
runs after `--warmups`.

计时与内存分通道测量：计时重复不开启 tracemalloc，wall time 干净，且每轮计时前清空
tokenizer 文本缓存，每次计时都从零缓存开始——与生产语义一致（文本缓存按请求隔离、
跨文档不可复用）。warmup 仅用于加载 tokenizer 后端并让解释器/分配器达到稳态，不会
预热计时轮的缓存。内存通道每轮重建 splitter 并配全新 tokenizer 缓存
（`--memory-reps`），记录 split 单独与 split+finalize 两个峰值。每篇文档在
`--warmups` 次预热后重复 `--repetitions` 次，同时报告中位数与均值。

Two dataset modes combine in one run:

- **Synthetic shapes** — seeded generators with six structural profiles
  (deep-tree, wide-flat, long-sections, oversized-blocks, tiny-sections,
  edge-degenerate). Body sentinels must survive in some chunk, code sentinels
  must appear in exactly one chunk (no loss or duplication), and
  word-level recall against the parsed tree must stay ≥ 0.99.
- **Recombined real corpora** — section spans sampled from the fetched external
  Markdown corpora (Kubernetes docs, CommonMark cases, local element cases)
  and stitched into new documents, checked with the same word-recall oracle.

数据集双模式：

- **合成形态** — 种子化生成器提供六种结构画像（深树、宽扁平、长章节、超大块、
  微小节、退化边角）。正文哨兵必须保留在某个 chunk 中，代码哨兵必须恰好出现在
  一个 chunk（无丢失、无重复），对解析树的词级 recall 须 ≥ 0.99。
- **真实语料重组** — 从已 fetch 的外部 Markdown 语料（Kubernetes 文档、
  CommonMark 样例、本地 element cases）抽取章节片段拼接成新文档，使用同一
  词级 recall oracle。

```bash
# Fetch the pinned corpora first (only needed for recombined mode).
uv run python -m benchmarks.fetch_parser_corpora

# Full default run: 6 shapes x 10 docs + 30 recombined, approx + tiktoken.
uv run python -m benchmarks.splitter_random_run

# Parameter axis: re-run the same matrix under a different max_tokens budget.
uv run python -m benchmarks.splitter_random_run --max-tokens 1200 \
  --warmups 2 --repetitions 5 --memory-reps 3 \
  --output benchmarks/results/splitter-full-b1200

# Quick synthetic-only run (no fetched corpora required).
uv run python -m benchmarks.splitter_random_run \
  --corpus synthetic \
  --shapes deep-tree,oversized-blocks \
  --documents-per-shape 3 \
  --tokenizers approx \
  --warmups 0 --repetitions 1 --memory-reps 0

# Focus on one topology pair with the realistic encoder.
uv run python -m benchmarks.splitter_random_run \
  --corpus both \
  --splitters incremental-subtree,exact-subtree \
  --tokenizers tiktoken
```

`summary.json` reports overall / by-tokenizer / by-splitter / by-dataset
aggregates plus a pairwise exact-vs-incremental table (wall-time ratio,
count-call ratio, memory ratio, estimate-error and budget-violation
comparison). The process exits non-zero when any oracle fails. Exact counting
never enables the tokenizer cache: every document's split starts from a zero
cache in production, and a single split offers essentially no cache reuse, so
the recount pays full encoding every time while incremental pays a fixed
pre-measure pass — all wall times are cold-cache numbers. Over-budget chunks
reported by both counting modes are identical and come from atomic units that
exceed the budget — `edge-degenerate`'s long-title variant and, once the
Kubernetes corpus joins the recombined pool, oversized table/list blocks from
real pages. A heading or a table is an atomic unit that cannot be split
internally.

`summary.json` 提供总体 / 按 tokenizer / 按 splitter / 按数据集的汇总，以及 exact
与 incremental 的配对对比表（耗时比、计数调用比、内存比、估计误差与超预算率对
比）。任何 oracle 失败时进程以非零码退出。exact 计数完全不启用 tokenizer 缓存：
生产中每篇文档的 split 都从零缓存开始、单篇内基本不存在缓存复用，因此 exact 的
每次重计数都支付完整编码成本，incremental 则支付一次性预测量开销——所有耗时均为
冷缓存口径。两种计数方式报告的超预算块均来自 `edge-degenerate` 的“超长标题”
变体——标题是原子单元，无法在标题内部切分。

### Full comparison report / 完整对比报告

`splitter_report.py` renders a self-contained Chinese HTML report from several
`splitter_random_run` output directories plus the cache probe:

```bash
# After running the matrix under budgets 300/600/1200 with --output
# benchmarks/results/splitter-full-b{BUDGET}, and (optionally) producing
# splitter-cache-probe.json via a focused tiktoken LRU-capacity experiment:
uv run python -m benchmarks.splitter_report
```

The report covers dataset length profiles, length × time tables per
engine/budget, accuracy tables (estimate error, violation rate, recall),
cold-run memory peaks per dataset/splitter, a tiktoken cache-capacity
irrelevance probe, auto-derived key findings, and an editorial summary &
evaluation section (per-dimension verdicts, splitter selection guidance, and
measurement-scope caveats). Every measured section also carries interactive
ECharts figures — budget × splitter time bars, a per-document length × time
scatter, incremental estimate-error bars, exact/incremental paired ratios
against a 1.0 reference line, cold-run memory bars, and the cache LRU
comparison — with button selectors for engine/budget/metric, hover tooltips,
and toggleable legend series, so cross-dimension comparisons that are hard to
read row-by-row in a table are visible at a glance. Metric definitions are
typeset as LaTeX and rendered with an inlined KaTeX. One known result: a
single split of the ~50 KB probe document touches ~1900 distinct `count()`
texts; under the cold-cache timing semantics (cache cleared before every
repetition) the default `max_cache_size=1000` and an enlarged `10000` measure
identically (speedup 1.0x for all six variants) — no splitter depends on
intra-split LRU reuse, and no cache tuning is needed for large documents.

Chart/LaTeX vendor libraries (pinned ECharts 5.6.0 and KaTeX 0.16.21, including
the woff2 fonts, embedded as base64 data URIs) live in the git-ignored
`benchmarks/assets/vendor/` directory and are downloaded automatically on the
first render, keeping the emitted HTML fully self-contained and offline
viewable.

`splitter_report.py` 从多个 `splitter_random_run` 输出目录与缓存探测数据渲染一份
自包含的中文 HTML 报告：数据集长度画像、每引擎/预算的长度 × 时间表、准确率表
（估计误差、超限率、召回率）、每数据集/splitter 的冷启动内存峰值、tiktoken 缓存
容量无关性探测、自动生成的关键发现，以及「总结与评价」章节（分维度评价、选型建
议与测量口径局限）。每个测量章节另配可交互的 ECharts 图表——预算 × 变体的耗时
柱状图、逐文档的长度 × 耗时散点图、incremental 估计误差柱状图、exact/incremental
配对比值图（带 1.0 参考线）、冷启动内存柱状图与缓存 LRU 对比图——支持按钮切换
引擎/预算/统计量、悬停查数值、图例开关系列，表格里逐行难以横向对比的维度在图
上一眼可比；度量定义用 LaTeX 书写并由内联 KaTeX 渲染。已知结论之一：~50 KB 探测
文档单次 split 会触及约 1900 个不同的 `count()` 文本；在冷缓存计时口径（每轮计时
前清空缓存）下，默认 `max_cache_size=1000` 与扩容到 10000 的耗时完全一致（六个
变体加速比均为 1.0x）——没有任何变体依赖单篇内的 LRU 复用，大文档也无需调整
缓存配置。

图表与 LaTeX 的 vendor 库（固定版本 ECharts 5.6.0 与 KaTeX 0.16.21，含以 base64
data URI 内嵌的 woff2 字体）存放在被 Git 忽略的 `benchmarks/assets/vendor/`
目录，首次渲染时自动下载，产出的 HTML 保持完全自包含、可离线查看。

## Optional competitors / 可选竞品

Competitor adapters are never installed by the core package. The harness
supplies LangChain Recursive/Markdown, Unstructured basic/by-title, Docling
hierarchical, and Chonkie recursive adapters when their respective packages are
installed. Missing dependencies produce a clear skip/error instead of silently
changing the comparison.

竞品 adapter 不会被核心包安装。当前可使用 LangChain Recursive/Markdown、
Unstructured basic/by-title、Docling hierarchical 和 Chonkie recursive adapter。
依赖缺失会明确报错/跳过，绝不静默改变比较。
