# 安装

[English](../../getting-started/installation.md)

Lumberjack 支持 Python 3.10 及更高版本。PyPI distribution 名称为 `lumberjack-py`，Python import 仍为 `lumberjack`，命令行为 `lumber`。

```bash
pip install lumberjack-py
```

按应用需要安装可选功能：

| 功能 | 命令 | 包含内容 |
| --- | --- | --- |
| 精确/模型 tokenizer | `pip install "lumberjack-py[tokenizers]"` | `tiktoken`、`transformers` 和 token 缓存 |
| DOCX 输入 | `pip install "lumberjack-py[docx]"` | `python-docx` |
| Web 服务 | `pip install "lumberjack-py[web]"` | FastAPI、Uvicorn 和 multipart 支持 |
| 全部功能 | `pip install "lumberjack-py[all]"` | 所有可选功能 |

贡献者可通过 [uv](https://docs.astral.sh/uv/) 安装仓库：

```bash
uv sync --group dev --group test --extra tokenizers --extra docx --extra web
```

接着阅读[快速开始](quickstart.md)。
