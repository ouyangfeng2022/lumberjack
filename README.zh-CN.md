<p align="center">
  <img src="assets/lumberjack-logo.svg" width="160" alt="Lumberjack 标志：斧头、文档、松树和年轮" />
</p>

# Lumberjack

[![PyPI](https://img.shields.io/pypi/v/lumberjack-py.svg)](https://pypi.org/project/lumberjack-py/)
[![Python](https://img.shields.io/pypi/pyversions/lumberjack-py.svg)](https://pypi.org/project/lumberjack-py/)
[![Docs](https://img.shields.io/badge/docs-GitHub%20Pages-4051b5)](https://ouyangfeng2022.github.io/lumberjack/)
[![CI](https://github.com/ouyangfeng2022/lumberjack/actions/workflows/ci.yml/badge.svg)](https://github.com/ouyangfeng2022/lumberjack/actions/workflows/ci.yml)

Lumberjack 是面向检索增强生成（RAG）的文档预处理库，可将文档转换为符合 token 预算的文本块，同时保留文档结构和来源信息，并支持按行拆分表格及配置表头重复策略。

Lumberjack 提供 Python API、命令行和 Web API 三种使用方式，并通过可选适配器支持 LangChain、LlamaIndex 和 Haystack。

[English README](README.md) · [中文文档站](https://ouyangfeng2022.github.io/lumberjack/zh-CN/) · [PyPI](https://pypi.org/project/lumberjack-py/)

## 三种使用方式

### 1. Python API

可向 `Lumberjack.saw()` 传入文本、字节、文件路径或 `Document`，获取解析后的文档及最终切片。

```python
from lumberjack import Lumberjack

result = Lumberjack(max_tokens=500).saw("""
# 部署

通过已批准的发布流程部署服务。
""")

for chunk in result.chunks:
    print(chunk.body, chunk.token_count)
```

多个文档可通过 `saw_many()` 迭代处理并逐项获取结果。详见 [Python API 参考](https://ouyangfeng2022.github.io/lumberjack/zh-CN/reference/python/)。

### 2. 命令行

将文件、目录或 glob 路径传给 `lumber`。命令行以 JSON 格式输出结果，并支持批量处理及按输入文档分别写出结果文件。

```bash
pip install lumberjack-py
lumber handbook.md --max-tokens 1200
lumber 'docs/**/*.md' --recursive --output-dir chunks/
```

可通过 `--input-format` 显式指定解析格式。对于 CSV、TSV、JSONL、日志等行或记录型输入，应选择 `--splitter record`。完整参数见 [CLI 参考](https://ouyangfeng2022.github.io/lumberjack/zh-CN/reference/cli/)。

### 3. Web API

安装 `web` extra 并启动服务后，可通过 HTTP 提交文本或上传文件，服务以 JSON 格式返回切片结果。

```bash
pip install 'lumberjack-py[web]'
lumberjack-serve --host 127.0.0.1 --port 9612
```

接口为 `POST /lumber/api/split/text` 和 `POST /lumber/api/split/file`。服务启动后可在 `http://127.0.0.1:9612/docs` 查看交互式接口文档。

## 功能特点

- **格式覆盖广。** 支持 Markdown、HTML、DOCX、纯文本与日志、CSV/TSV、JSON/JSONL、XML、YAML/TOML、XLSX、SQLite/SQL、源代码和 Jupyter Notebook，并统一解析为共享文档模型。DOCX、XLSX、模型 tokenizer 和增强代码解析需要安装相应可选依赖。
- **保留结构与来源信息。** 标题上下文随切片保留；记录型输入保留行、字段、工作表和来源位置信息，而不是转换为虚构章节。
- **按行拆分表格。** Markdown 和 HTML 表格在行边界拆分。默认在生成的每个切片中重复表头，并可按表格类型配置。
- **遵循内容边界。** 代码围栏拆分后仍保留围栏；列表和其他内容块采用相应的拆分策略。无法安全拆分的受保护内容可能超过设定的 token 预算。
- **切片组织方式可配置。** 可选择同级章节打包、优先保留子树、逐节处理，或对扁平输入按记录打包。
- **提供 token 预算控制。** 默认近似 tokenizer 无需下载模型；也可使用 `tiktoken` 或 Transformers tokenizer 进行模型级计数。精确计数和增量计数模式可分别选择。

## 支持的输入格式

| 类型 | 格式 | 说明 |
| --- | --- | --- |
| 文档 | Markdown、HTML、DOCX | 支持标题、段落、列表、表格、代码；可读取的文档属性也会保留。 |
| 文本与记录 | TXT、LOG、CSV、TSV、JSON、JSONL、XML、YAML、TOML | 记录格式保留逻辑行号和字段路径；扁平记录使用 `record` splitter。 |
| 电子表格与数据库 | XLSX、SQLite、SQL dump | SQLite 使用标准库。 |
| 代码与 Notebook | Python、JavaScript/TypeScript、Bash、C/C++、C#、Go、Java、Kotlin、Lua、PHP、Ruby、Rust、Swift、Zig、Jupyter Notebook | 安装 `code-parsing` extra 后可使用 Tree-sitter 声明边界和语法错误恢复。 |

目前不支持 RTF、ODT、旧版 Excel、PDF、图像、演示文稿和列式存储格式。

## 表格拆分

表格作为结构化内容块处理。表格超过块级预算时，Lumberjack 按完整行组合为多个切片；默认在每个切片中重复 Markdown 表头和分隔行，HTML 表格则重复表头。设置 `repeat_header=False` 可省略后续切片中的表头。若单行内容本身超过预算，该行仍会完整保留，因此对应切片可能超出预算。

Python 中可以为 Markdown 表格配置单独预算和表头策略：

```python
from lumberjack import Lumberjack
from lumberjack.block import MarkdownTableConfig
from lumberjack.splitter import SectionSplitter
from lumberjack.tokenizer import ApproxByteTokenizer

tokenizer = ApproxByteTokenizer()
splitter = SectionSplitter(
    tokenizer,
    max_tokens=500,
    block_options=[MarkdownTableConfig(repeat_header=True, max_tokens=300)],
)
result = Lumberjack(tokenizer=tokenizer, splitter=splitter).saw("report.md")
```

CLI 可用 `--block table:repeat-header=false,max-tokens=300` 设置相同选项。HTML 表格在 Python 中使用 `HTMLTableConfig`，CLI 中使用 `html_table`。

## 选择 splitter

| Splitter | 行为 |
| --- | --- |
| `section`（默认） | 独立处理每个章节的直接正文。 |
| `subtree` | 在预算允许时尽量保留完整章节子树。 |
| `sibling` | 在预算允许时打包相邻同级章节。 |
| `record` | 按行或记录打包 CSV/TSV、JSONL、日志等扁平输入。 |

`exact-*` 变体在规划时重新计数候选文本；默认及 `incremental-*` 变体在规划时使用增量计数，并在最终结果中提供权威计数。Tokenizer 的选择与计数模式互相独立。

## 安装可选功能

```bash
# 模型 tokenizer、Web API 和 Tree-sitter 解析
pip install 'lumberjack-py[tokenizers,web,code-parsing]'

# RAG 框架集成
pip install 'lumberjack-py[langchain,llama-index,haystack]'
```

框架适配器位于 `lumberjack.integrations`，可将切片转换为框架文档或节点，也提供原生 splitter/parser 组件。详见[集成指南](https://ouyangfeng2022.github.io/lumberjack/zh-CN/guides/integrations/)。

## 更多内容

- [核心概念](https://ouyangfeng2022.github.io/lumberjack/zh-CN/concepts/pipeline/) — 文档解析、切片、渲染和来源 metadata。
- [配置指南](https://ouyangfeng2022.github.io/lumberjack/zh-CN/guides/configuration/) — block 策略和 token 预算控制。
- [自定义组件](https://ouyangfeng2022.github.io/lumberjack/zh-CN/guides/custom-components/) — parser、tokenizer、splitter 和后处理阶段。
- [参与贡献](CONTRIBUTING.md) · [安全策略](SECURITY.md) · [许可证](LICENSE)
