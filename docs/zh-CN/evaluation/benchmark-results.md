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

入库语料为每类场景提供五份 CC0 文档，另附三组 Markdown/HTML 跨格式等价组。该规
模面向可重复的工具验证，不用于头条数字。仅可在讨论的同一提交上运行语料并在此链
接确切结果目录后，才可发布结论。首份已发布基线见下文。

## 已发布基线 — 2026-09-03

在提交 `7735d5828f38` 上以完整 adapter 集合测量：两种 lumberjack 计数模式加九个
竞品变体。结果保存在 `benchmarks/results/20260903-7735d5828f38/`（可用下方命令重
新生成）；聚合器 `benchmarks/compare.py` 从各 run 的 `raw.json` 生成
`summary.json` 与 `comparison.md`，并在原生 oracle 失败时以非零码退出。

### 环境

| 项目 | 值 |
| --- | --- |
| 提交 | `7735d5828f38`（`dev`） |
| 日期 | 2026-09-03 |
| 操作系统 / CPU | Linux（WSL2），AMD Ryzen 7 5800H，8 线程 |
| Python | 3.12.3 |
| Lumberjack 依赖 | markdown-it-py 4.0.0、tiktoken 0.12.0 |
| 竞品 | langchain-text-splitters 1.1.2、unstructured 0.25.2、docling 2.120.3（docling-core 2.91.0）、chonkie 1.7.0 |
| 数据集 | `2026.08.27` — 36 份文档，六个场景 + 三组跨格式等价对（共约 33 KB） |
| 配置 | `max_tokens=240`，1 次预热，5 次重复；token 单位 = UTF-8 字节 ÷ 3 |

预算等价性：`langchain-recursive` 使用 bytes/3 长度函数配 `chunk_size=240`；两个
chonkie chunker 使用按字节计数的 `ByteTokenizer` 配 `chunk_size=720` 字节；
`docling-hybrid` 使用离线 bytes/3 `BaseTokenizer`，其 `get_max_tokens()` 返回
240。`langchain-markdown` / `langchain-html` 是无预算参数的标题切分器，
`docling-hierarchical` 按设计没有预算参数——它们的超预算是工具在等价预算要求下
的真实行为。

### 质量（36 份文档均值）

| Run | 内容 recall | 预算违规 | 块断裂 | 重复率 | 利用率 | chunk 数 | token p50 / p95 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| `lumberjack`（section，增量） | 1.000 | 0.000 | 0.000 | 0.000 | 0.277 | 194 | 49 / 162 |
| `lumberjack`（exact-section） | 1.000 | 0.000 | 0.000 | 0.000 | 0.277 | 194 | 49 / 162 |
| `langchain-recursive` | 1.000 | 0.000 | 0.000 | 0.000 | 0.646 | 67 | 173 / 226 |
| `langchain-markdown` | 1.000 | 0.083 | 0.000 | 0.000 | 0.354 | 165 | 44 / 186 |
| `langchain-html` | 1.000 | 0.611 | 0.000 | 0.000 | 0.761 | 67 | 54 / 516 |
| `unstructured-basic` | 0.986 | 0.000 | 0.028 | 0.003 | 0.111 | 433 | 8 / 84 |
| `unstructured-by-title` | 0.986 | 0.000 | 0.028 | 0.000 | 0.403 | 117 | 62 / 166 |
| `docling-hierarchical` | 0.153 | 0.013 | 0.028 | 0.000 | 0.252 | 200 | 31 / 170 |
| `docling-hybrid` | 0.153 | 0.000 | 0.028 | 0.000 | 0.274 | 190 | 34 / 173 |
| `chonkie-recursive` | 1.000 | 0.000 | 0.000 | 0.000 | 0.656 | 66 | 172 / 236 |
| `chonkie-table` | 0.597 | 0.125 | 0.000 | 0.000 | 0.449 | 42 | 209 / 333 |

只有 lumberjack 的 run 为每个 chunk 同时输出起止源行号（`provenance_coverage`
1.0）；没有竞品 adapter 输出行级 provenance，因此该列不可比，此处不列出。

### 性能（5 次重复的中位数）

| Run | 总耗时（36 份文档） | 单文档均值 | 吞吐量 | 分配峰值 | count 调用 |
| --- | ---: | ---: | ---: | ---: | ---: |
| `lumberjack`（section，增量） | 0.184 s | 5.1 ms | 0.180 MB/s | 0.5 MB | 1878 |
| `lumberjack`（exact-section） | 0.161 s | 4.5 ms | 0.206 MB/s | 0.5 MB | 487 |
| `lumberjack`（section，tiktoken） | 0.204 s | 5.7 ms | 0.162 MB/s | 0.5 MB | 1845 |
| `lumberjack`（exact-section，tiktoken） | 0.190 s | 5.3 ms | 0.174 MB/s | 0.5 MB | 466 |
| `langchain-recursive` | 0.003 s | 0.1 ms | 9.621 MB/s | 0.0 MB | 0 |
| `langchain-markdown` | 0.014 s | 0.4 ms | 2.305 MB/s | 0.0 MB | 0 |
| `langchain-html` | 0.022 s | 0.6 ms | 1.497 MB/s | 0.1 MB | 0 |
| `unstructured-basic` | 0.512 s | 14.2 ms | 0.065 MB/s | 0.2 MB | 0 |
| `unstructured-by-title` | 0.562 s | 15.6 ms | 0.059 MB/s | 0.2 MB | 0 |
| `docling-hierarchical` | 9.559 s | 265.5 ms | 0.003 MB/s | 0.5 MB | 0 |
| `docling-hybrid` | 9.822 s | 272.8 ms | 0.003 MB/s | 0.5 MB | 0 |
| `chonkie-recursive` | 0.008 s | 0.2 ms | 4.348 MB/s | 0.0 MB | 0 |
| `chonkie-table` | 0.005 s | 0.1 ms | 6.654 MB/s | 0.0 MB | 0 |

docling 的耗时由文档转换主导而非 chunking；应把它的墙钟时间视为 36 份小文档上的
转换成本，而不是 chunker 速度结论。`count_calls` 只统计 lumberjack 的 tokenizer
调用。

### 计数模式（仅 lumberjack）

在同一 tokenizer 下，exact 与增量计数输出了完全相同的 chunk 集合（`approx` 下
194 个，`tiktoken` 下 190 个）。增量估算在本语料上与最终计数几乎一致：`approx`
下平均相对误差 0.00013，`tiktoken` 下全部 190 个 chunk 偏差恰好为零。更大规模下，
随机 splitter 基准（`benchmarks/splitter_random_run.py`）测得 `tiktoken` 平均绝对
估算误差 0.003 token、最大 2.0 token。本语料上 exact 计数的 tokenizer `count`
调用更少（`approx` 下 487 对 1878；`tiktoken` 下 466 对 1845），墙钟时间相当。

### 结论

1. **结构感知的预算装箱是唯一同时守住五项不变量的参赛者。** 两种 lumberjack
   计数模式在内容 recall 1.0 的同时做到零预算违规、零重复 payload、零 protected
   block 断裂和完整行级 provenance。同一语料、同一预算下，每个竞品至少放弃其中
   一项。
2. **窗口装箱器利用率更高但不输出结构。** `langchain-recursive` 与
   `chonkie-recursive` 把窗口装得很满（利用率 0.646 / 0.656），本语料上零违规，
   但 chunk 不带标题上下文与 provenance，边界跟随分隔符而非文档结构。lumberjack
   保持标题与原子表格/代码完整，在 `max_tokens=240` 下产生更多更小的 chunk（利用
   率 0.277）——这是永不破坏 protected block 的有意代价。
3. **Docling 把标题放在元数据而不是 chunk 文本。** docling 两个 run 的全部 61 个
   recall 缺失项都是标题字符串或原始 Markdown 表头签名，没有丢失任何正文散文
   （已逐文档核实）。`docling-hybrid` 遵守换算后的预算；`docling-hierarchical`
   没有预算参数，1.3% 的结构 chunk 超出预算。
4. **无预算的标题切分器在长章节上溢出。** `langchain-markdown` 保留标题但 8.3%
   的 chunk 超预算；`langchain-html` 只适用于 HTML 输入——在本语料的 Markdown
   主体上退化为整篇一个 chunk（61.1% 违规）。
5. **元素级切分碎片化文档。** `unstructured-basic` 输出 433 个 chunk、中位数仅
   8 token（利用率 0.111），并把 protected block 拆散到多个元素（2.8%）；
   `unstructured-by-title` 装箱更满（0.403），protected block 断裂相同。
6. **`chonkie-table` 是表格特化工具。** 在 tables 场景 recall 完美，但在其他场景
   丢失标题文本（整体 0.597——缺失项全部是标题，无正文），且 12.5% 的 chunk 因
   合并行超预算。
7. **计数模式是成本旋钮而非质量旋钮。** 本语料上两种模式输出相同 chunk；增量估算
   基本精确（规模化后误差 ≤ 2 token），exact 计数以更少的 tokenizer 调用换取完整
   重计数。

### 已知不可比项

- 没有竞品 adapter 输出行级 provenance；`provenance_coverage` 以 0 上报并附诊断说
  明，不参与结论。
- 所有参赛者的 token 单位都是 UTF-8 字节 ÷ 3；各工具的预算按上文描述换算。生产中
  的 BPE tokenizer 会改变绝对 token 数，不改变相对行为。
- 数据集标注包含标题字符串和原始表头行；把标题保留在元数据中的工具（docling）或
   丢弃标题的工具（chonkie-table）会在这些标注项上被 `content_recall` 扣分——逐项
   缺失已公布在上方，扣分可审计。
- 单机、每 adapter 单个预热进程、5 次重复取中位数。语料（约 33 KB、36 份文档）面
  向可重复的 harness 验证；规模化的结论需参照随机 splitter 基准。

### 复现

```bash
uv sync --group dev --group test --group benchmark \
  --extra tokenizers --extra docx --extra web
BASE="benchmarks/results/$(date +%Y%m%d)-$(git rev-parse --short=12 HEAD)"
uv run python -m benchmarks.run --adapter lumberjack --splitter section \
  --output "$BASE/lumberjack"
uv run python -m benchmarks.run --adapter lumberjack --splitter exact-section \
  --output "$BASE/lumberjack-exact-section"
uv run python -m benchmarks.run --adapter lumberjack --splitter section \
  --tokenizer tiktoken --output "$BASE/lumberjack-tiktoken"
uv run python -m benchmarks.run --adapter lumberjack --splitter exact-section \
  --tokenizer tiktoken --output "$BASE/lumberjack-exact-section-tiktoken"
for adapter in langchain-recursive langchain-markdown langchain-html \
  unstructured-basic unstructured-by-title docling-hierarchical \
  docling-hybrid chonkie-recursive chonkie-table; do
  uv run python -m benchmarks.run --adapter "$adapter" --output "$BASE/$adapter"
done
uv run python -m benchmarks.compare "$BASE"
```
