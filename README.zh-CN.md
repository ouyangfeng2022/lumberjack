<p align="center">
  <img src="assets/lumberjack-logo.svg" width="160" alt="Lumberjack 标志：斧头、文档、松树和年轮" />
</p>

# Lumberjack

[![PyPI](https://img.shields.io/pypi/v/lumberjack-py.svg)](https://pypi.org/project/lumberjack-py/)
[![Python](https://img.shields.io/pypi/pyversions/lumberjack-py.svg)](https://pypi.org/project/lumberjack-py/)
[![Docs](https://img.shields.io/badge/docs-GitHub%20Pages-4051b5)](https://ouyangfeng2022.github.io/lumberjack/)
[![CI](https://github.com/ouyangfeng2022/lumberjack/actions/workflows/ci.yml/badge.svg)](https://github.com/ouyangfeng2022/lumberjack/actions/workflows/ci.yml)

**把 Markdown、HTML 和 DOCX 切成适合检索的 Chunk，同时保留文档结构与标题上下文。**

Lumberjack 是用于 RAG 预处理的 Python 库和 CLI。它先读取文档树而不是直接切纯文本，保留标题与来源元数据，尊重表格和围栏代码块；只要内容可安全拆分，就会让 Chunk 保持在 token 预算内。

[English README](README.md) · [中文文档站](https://ouyangfeng2022.github.io/lumberjack/zh-CN/) · [PyPI](https://pypi.org/project/lumberjack-py/)

## 为什么使用 Lumberjack？

- **上下文不会丢失。** Chunk 将标题元数据与正文分开保存，检索时仍可还原答案所属章节。
- **先理解结构。** Markdown、HTML 和 DOCX 会先转成统一、格式中立的 `DocTree`。
- **预算更实用。** 默认 splitter 用快速增量估算规划，最后记录权威 token 计数。
- **Chunk 形状可选。** 可打包同级章节、优先保留子树，或独立处理每个章节的直接正文。

## 安装

```bash
pip install lumberjack-py

# 精确 tokenizer、DOCX 支持和 Web API
pip install "lumberjack-py[tokenizers,docx,web]"
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
# 根据后缀推断 Markdown、HTML 或 DOCX。
lumber handbook.md --max-tokens 1200

# 输出适合入库任务消费的 JSON。
lumber report.docx --tokenizer tiktoken --splitter subtree > chunks.json
```

完整参数与默认值请见 [CLI 参考](https://ouyangfeng2022.github.io/lumberjack/zh-CN/reference/cli/)。

## 选择 splitter

| Splitter | 适用场景 |
| --- | --- |
| `sibling`（默认） | 希望尽量填满 Chunk，并允许相邻同级章节共享上下文。 |
| `subtree` | 只要预算允许，就让完整的章节子树保持在一起。 |
| `section` | 需要独立考虑每个章节的直接正文。 |

| 计量模式 | 行为 |
| --- | --- |
| 无前缀 / `incremental-*` | 规划时快速增量估算，最终仍给出权威计数。 |
| `exact-*` | 规划时对每个渲染候选项完整重计。 |

Tokenizer 与计量模式互不绑定，例如 `tiktoken` 可配合 `incremental-sibling`。生产环境调优前，请先阅读 [splitter 选择指南](https://ouyangfeng2022.github.io/lumberjack/zh-CN/concepts/splitting/)。

## Web API

```bash
lumberjack-serve --reload
```

安装 `web` extra 后，服务提供 `POST /lumber/api/split/text`（Markdown/HTML JSON）和 `POST /lumber/api/split/file`（上传 Markdown、HTML 或 DOCX）。运行时可从 [`/docs`](http://127.0.0.1:9612/docs) 打开 FastAPI 的交互式 OpenAPI 文档。

## 深入了解

- [核心概念](https://ouyangfeng2022.github.io/lumberjack/zh-CN/concepts/pipeline/) — `Document` 到 `Chunk`、渲染、预算和来源 metadata。
- [配置指南](https://ouyangfeng2022.github.io/lumberjack/zh-CN/guides/configuration/) — block 策略与预算控制。
- [自定义组件](https://ouyangfeng2022.github.io/lumberjack/zh-CN/guides/custom-components/) — parser、tokenizer、splitter 与后处理阶段。
- [Python API 参考](https://ouyangfeng2022.github.io/lumberjack/zh-CN/reference/python/)
- [参与贡献](CONTRIBUTING.md) · [安全策略](SECURITY.md) · [许可证](LICENSE)

Benchmark 报告仍在建设中；项目不会发布未经验证的质量或性能结论。
