<p align="center">
  <img src="assets/lumberjack-logo.svg" width="160" alt="Lumberjack 标志：斧头、文档、松树和年轮" />
</p>

# Lumberjack

[![PyPI](https://img.shields.io/pypi/v/lumberjack.svg)](https://pypi.org/project/lumberjack/)
[![Python](https://img.shields.io/pypi/pyversions/lumberjack.svg)](https://pypi.org/project/lumberjack/)
[![CI](https://github.com/ouyangfeng2022/lumberjack/actions/workflows/ci.yml/badge.svg)](https://github.com/ouyangfeng2022/lumberjack/actions/workflows/ci.yml)

**把长篇结构化文档切成适合检索的 Chunk，同时保留回答问题所需的上下文。**

Lumberjack 是用于 RAG 的 Python 库和 CLI。它理解文档结构，把标题与其正文关联起来，
尊重表格和代码块，并只在超出 token 预算时拆分文档。

[English README](README.md)

## 为什么使用 Lumberjack？

朴素文本分割器只按字符或 token 边界切分：标题可能和正文分离，表格可能被从中间截断，
相邻但无关的主题也可能被拼到同一个 Chunk。Lumberjack 则基于统一的文档树工作：

- **保留上下文。** 每个 Chunk 都携带标题路径和来源元数据。
- **尊重结构。** 标题、段落、列表、表格和围栏代码块会作为文档块处理，而不是无结构文本。
- **更有效地使用预算。** 默认 splitter 在打包 section 时使用低成本的增量估算，最后再给出权威 token 计数。
- **按需要组织 Chunk。** 可以打包同级 section、优先保留完整子树，或单独处理 section 的直接正文。

当前支持 Markdown、HTML 和 DOCX。

## 安装

```bash
pip install lumberjack

# 可选的精确 tokenizer、DOCX 支持和 Web API
pip install "lumberjack[tokenizers,docx,web]"
```

需要 Python 3.10 或更高版本。

## 快速开始

把文档内容、bytes 或 `Path` 传给 `Lumberjack.saw()`：

```python
from pathlib import Path

from lumberjack import Lumberjack

jack = Lumberjack(max_tokens=1200)
chunks = jack.saw(Path("handbook.md"))

for chunk in chunks:
    print(chunk.own_heading, chunk.body, chunk.token_count)
```

内存中的内容可直接传入字符串。普通字符串始终表示内容，不会被当作文件路径：

```python
chunks = Lumberjack(max_tokens=500).saw(
    "# Deployment\n\nDeploy the service with the approved release workflow."
)
```

每个结果都是 `Chunk` dataclass：`body` 是渲染后的正文；`ancestor_headings` 与
`own_heading` 保留 section 上下文；`token_count` 是输出处理后的最终计数。标题、来源路径和
行号范围也会在可用时保留。

## 命令行使用

```bash
# 根据文件后缀推断格式。
lumber handbook.md --max-tokens 1200

# 按需选择 tokenizer 或 splitter。
lumber report.docx --input-format docx --tokenizer tiktoken --splitter subtree

# JSON Chunk 输出到标准输出。
lumber page.html --input-format html --splitter exact-sibling
```

CLI 输出 JSON，可直接接入索引或入库任务。

## 选择分割策略

| 策略 | 适合的需求 |
| --- | --- |
| `sibling`（默认） | 尽量填满 Chunk，同时打包相邻的同级 section 并保留共享上下文。 |
| `subtree` | 只要预算允许，就让完整的 section 子树保持在一起。 |
| `section` | 独立处理每个 section 的直接正文。 |

默认策略使用增量估算来快速做预算决策。若每次拆分决策都必须精确重计渲染结果，请使用
`exact-sibling`、`exact-subtree` 或 `exact-section`。无论何种策略，最终 Chunk 都会有权威计数。

具体的策略示例请见[分割策略说明](docs/splitter-strategies.zh-CN.md)。

## Web API

安装 `web` extra 后启动服务：

```bash
lumberjack-serve --reload
```

服务提供 `POST /lumber/api/split/text`，用于粘贴 Markdown 或 HTML；还提供
`POST /lumber/api/split/file`，用于上传 Markdown、HTML 或 DOCX。两者返回的序列化 Chunk
结构与 Python API 和 CLI 一致。

## 需要时再定制

默认配置可以直接使用。高级流水线可以向 `Lumberjack(...)` 注入自己的 parser、tokenizer、
splitter、normalizer 或 transformer。内置 splitter 接受类型安全的 `block_options`，可为表格、
代码围栏和自定义 block kind 设置隔离与预算策略。公开扩展点位于 `lumberjack.parser`、`lumberjack.tokenizer`、
`lumberjack.splitter`、`lumberjack.block` 和 `lumberjack.protocols`。

## 开发

```bash
uv sync --group dev --group test --extra tokenizers --extra docx --extra web
UV_CACHE_DIR=/tmp/uvcache uv run pytest
```

## 许可证

MIT
