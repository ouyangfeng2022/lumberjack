<p align="center">
  <img src="assets/lumberjack-logo.svg" width="160" alt="Lumberjack 标志：斧头、文档、松树和年轮" />
</p>

# Lumberjack

[![PyPI](https://img.shields.io/pypi/v/lumberjack-py.svg)](https://pypi.org/project/lumberjack-py/)
[![Python](https://img.shields.io/pypi/pyversions/lumberjack-py.svg)](https://pypi.org/project/lumberjack-py/)
[![Docs](https://img.shields.io/badge/docs-GitHub%20Pages-4051b5)](https://ouyangfeng2022.github.io/lumberjack/)
[![CI](https://github.com/ouyangfeng2022/lumberjack/actions/workflows/ci.yml/badge.svg)](https://github.com/ouyangfeng2022/lumberjack/actions/workflows/ci.yml)

**把文档和扁平记录切成适合检索的 Chunk，同时保留结构与来源信息。**

Lumberjack 是用于 RAG 预处理的 Python 库和 CLI。它先读取文档树而不是直接切纯文本，保留标题与来源元数据，尊重表格和围栏代码块；只要内容可安全拆分，就会让 Chunk 保持在 token 预算内。

[English README](README.md) · [中文文档站](https://ouyangfeng2022.github.io/lumberjack/zh-CN/) · [PyPI](https://pypi.org/project/lumberjack-py/)

## 为什么使用 Lumberjack？

- **上下文不会丢失。** Chunk 将标题元数据与正文分开保存，检索时仍可还原答案所属章节。
- **结构语义准确。** Markdown/HTML/DOCX 使用标题树；CSV/TSV、JSONL 和日志保持有序记录，不伪造章节。
- **预算更实用。** 默认 splitter 用快速增量估算规划，最后记录权威 token 计数。
- **Chunk 形状可选。** 可打包同级章节、优先保留子树，或独立处理每个章节的直接正文。

## 输入格式：当前与规划

下表的“规划中”是设计承诺，不是可安装功能承诺：在某个发行版将其标为“已支持”前，
请不要把它传给 `format`，也不要依赖自动格式检测。

| 格式族 | 格式 | 状态 | 目标结构模型 |
| --- | --- | --- | --- |
| 标记文档 | Markdown（`.md`、`.markdown`）、HTML（`.html`、`.htm`） | 已支持 | 标题、块、表格、列表、代码和来源行号。 |
| 文字处理文档 | DOCX（`.docx`） | 已支持 | 标题样式、段落、表格、列表和文档属性。 |
| 纯文本与富文本 | TXT（`.txt`、`.text`）、文本日志（`.log`） | 已支持 | TXT 使用段落/行；日志是原子有序记录。RTF 仍在规划中。 |
| OpenDocument 与旧式文字处理 | ODT、DOC | 规划中 | 在源格式提供时保留标题与内容块。 |
| 电子表格与分隔数据 | CSV（`.csv`）、TSV（`.tsv`）、XLSX（`.xlsx`，`spreadsheets` extra） | 已支持 | 表头 schema 加原子行，并保留 sheet/行/列来源。XLS 和 ODS 仍在规划中。 |
| 半结构化数据 | JSON（`.json`）、JSONL（`.jsonl`、`.ndjson`）、XML（`.xml`）、YAML（`.yaml`、`.yml`）、TOML（`.toml`） | 已支持 | 保留标量 key path、记录行和 XML 叶子元素路径；均为有序记录。 |
| 分析与数据库导出 | SQLite（`.sqlite`、`.sqlite3`、`.db`）、SQL dump（`.sql`） | 已支持 | SQLite 表/行来源和有序 SQL 语句。Parquet、Avro、ORC 已延后。 |
| 源代码与 Notebook | Python、JavaScript/TypeScript、Bash、C/C++、C#、Go、Java、Kotlin、Lua、PHP、Ruby、Rust、Swift、Zig 与 Jupyter Notebook | 已支持 | 安装 `code-parsing` 可获得 Tree-sitter 声明边界、语法错误恢复和来源位置；其他语言已延后。 |
| 演示文稿与电子书 | PPTX、PPT、ODP、EPUB | 规划中 | 幻灯片/页面、标题、备注和有序内容块。 |
| 邮件与归档 | EML、MSG、MBOX | 规划中 | 邮件头、正文、附件和会话来源信息。 |
| PDF 与图像 | PDF、PNG、JPG/JPEG、TIFF、WebP | 规划中 | 可用时使用原生 PDF 文本/版面；否则使用 OCR/版面块和页级来源信息。 |

平面数据是一级设计场景，而不是伪装成标题树。CSV、TSV、JSONL、Parquet 和以记录为中心的
JSON 将使用有序的 record/row 单元，并保留 schema 与字段路径 provenance。基于标题的策略，
例如同级 section 打包，对这些输入没有意义；其 adapter 必须选择面向 row/record 的打包，
在配置要求时保留完整的 protected row，并报告行号、列名、JSON path、页码或 sheet 等逻辑位置。
这只是规划行为，当前三个 parser 尚未实现。

## 查看流水线的每一步

当前 `Lumberjack.saw()` 返回 `SplitResult(document, chunks)`；需要中间 `DocTree` 或
`ChunkDraft` 时，集成方可分别调用公开的 parser、splitter 和 finalizer。

规划中的 pipeline trace API 会通过一个稳定结果公开每个内置和可选解析阶段：原始
`Document`、抽取结果（例如 OCR/版面）、规范化 `DocTree`、`ChunkDraft`、渲染文本、
规范化/转换后的文本和最终 `Chunk`。MinerU、Docling、PaddleOCR-VL、dots.mocr 等 PDF
视觉 parser 将作为可选集成，而不是核心依赖，并会保留页码、bounding box 和 parser provenance。

## 安装

```bash
pip install lumberjack-py

# 精确 tokenizer、DOCX/XLSX、Tree-sitter 代码解析和 Web API
pip install "lumberjack-py[tokenizers,docx,spreadsheets,code-parsing,web]"
```

需要 Python 3.10 或更高版本。

## 第一次拆分

```python
from lumberjack import Lumberjack

result = Lumberjack(max_tokens=500).saw("""
# 部署

通过已批准的发布流程部署服务。

## 回滚

健康检查通过前，请保留上一个镜像。
""")

for chunk in result.chunks:
    print(chunk.own_heading, chunk.body, chunk.token_count)
```

`result.document` 包含解析后的 `DocTree`、标题、metadata 和来源信息；每个 `Chunk` 包含正文、最终 `token_count`、标题上下文，以及可用时的来源行号。文件输入、输出处理和可选依赖请见[五分钟入门](https://ouyangfeng2022.github.io/lumberjack/zh-CN/getting-started/quickstart/)。

## 使用 CLI

```bash
# 根据后缀推断已支持的格式。
lumber handbook.md --max-tokens 1200

# CSV 行保持原子记录（TSV、JSONL 和日志同样使用）。
lumber people.csv --splitter record --max-tokens 1200

# 输出适合入库任务消费的 JSON。
lumber report.docx --tokenizer tiktoken --splitter subtree > chunks.json
```

完整参数与默认值请见 [CLI 参考](https://ouyangfeng2022.github.io/lumberjack/zh-CN/reference/cli/)。

## 选择 splitter

| Splitter | 适用场景 |
| --- | --- |
| `sibling` | 希望尽量填满 Chunk，并允许相邻同级章节共享上下文。 |
| `subtree` | 只要预算允许，就让完整的章节子树保持在一起。 |
| `section`（默认） | 需要独立考虑每个章节的直接正文。 |

| 计量模式 | 行为 |
| --- | --- |
| 无前缀 / `incremental-*` | 规划时快速增量估算，最终仍给出权威计数。 |
| `exact-*` | 规划时对每个渲染候选项完整重计。 |

Tokenizer 与计量模式互不绑定，例如 `tiktoken` 可配合 `incremental-sibling`。生产环境调优前，请先阅读 [splitter 选择指南](https://ouyangfeng2022.github.io/lumberjack/zh-CN/concepts/splitting/)。

## Web API

```bash
lumberjack-serve --reload
```

安装 `web` extra 后，服务提供 `POST /lumber/api/split/text`（UTF-8 Markdown、HTML、TXT、LOG、CSV/TSV、JSON/JSONL、XML、YAML）和 `POST /lumber/api/split/file`（前述格式及 DOCX、XLSX；XLSX 需安装 `spreadsheets`）。LOG、CSV/TSV/XLSX、JSON/JSONL、XML、YAML 需选择 `splitter: "record"`。上表其余“规划中”的格式目前不接受。运行时可从 [`/docs`](http://127.0.0.1:9612/docs) 打开 FastAPI 的交互式 OpenAPI 文档。

## 深入了解

- [核心概念](https://ouyangfeng2022.github.io/lumberjack/zh-CN/concepts/pipeline/) — `Document` 到 `Chunk`、渲染、预算和来源 metadata。
- [配置指南](https://ouyangfeng2022.github.io/lumberjack/zh-CN/guides/configuration/) — block 策略与预算控制。
- [自定义组件](https://ouyangfeng2022.github.io/lumberjack/zh-CN/guides/custom-components/) — parser、tokenizer、splitter 与后处理阶段。
- [Python API 参考](https://ouyangfeng2022.github.io/lumberjack/zh-CN/reference/python/)
- [参与贡献](CONTRIBUTING.md) · [安全策略](SECURITY.md) · [许可证](LICENSE)

Benchmark 报告仍在建设中；项目不会发布未经验证的质量或性能结论。
