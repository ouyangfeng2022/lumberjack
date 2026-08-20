# Installation

[中文](../zh-CN/getting-started/installation.md)

Lumberjack supports Python 3.10 and newer. Its PyPI distribution is named `lumberjack-py`, while the Python import remains `lumberjack` and the command line program is `lumber`.

```bash
pip install lumberjack-py
```

Install only the optional features your application needs:

| Feature | Command | Includes |
| --- | --- | --- |
| Exact/model tokenizers | `pip install "lumberjack-py[tokenizers]"` | `tiktoken`, `transformers`, and token caches |
| DOCX input | `pip install "lumberjack-py[docx]"` | `python-docx` |
| XLSX input | `pip install "lumberjack-py[spreadsheets]"` | `openpyxl` |
| Web service | `pip install "lumberjack-py[web]"` | FastAPI, Uvicorn, multipart support |
| Everything | `pip install "lumberjack-py[all]"` | All optional features |

For contributors, install the repository with [uv](https://docs.astral.sh/uv/):

```bash
uv sync --group dev --group test --extra tokenizers --extra docx --extra web
```

Next, follow the [quickstart](quickstart.md).
