# Web API 参考

[English](../../reference/web-api.md)

安装 Web extra 并启动服务：

```bash
pip install "lumberjack-py[web]"
lumberjack-serve --reload
```

服务在 [`http://127.0.0.1:9612/docs`](http://127.0.0.1:9612/docs) 提供交互式 OpenAPI 文档，在 [`http://127.0.0.1:9612/openapi.json`](http://127.0.0.1:9612/openapi.json) 提供 OpenAPI schema。

## Endpoint

| Endpoint | 输入 |
| --- | --- |
| `POST /lumber/api/split/text` | JSON：`text`、`input_format`（`markdown` 或 `html`）以及拆分选项。 |
| `POST /lumber/api/split/file` | multipart form：`file`、`input_format`（`auto`、`markdown`、`html` 或 `docx`）以及拆分选项。 |

两个 endpoint 都会返回 `document`、`metadata`、`reference_definitions`、`chunk_count`，以及与 Python `Chunk` model 对应的序列化 `chunks`。

```bash
curl -X POST http://127.0.0.1:9612/lumber/api/split/text \
  -H 'content-type: application/json' \
  -d '{
    "text": "# Guide\\n\\nKeep the heading with its paragraph.",
    "input_format": "markdown",
    "max_tokens": 500,
    "splitter": "sibling",
    "tokenizer": "approx"
  }'
```

Web API 与 CLI 使用相同的默认值和 splitter 名称。无效预算、不支持的格式、或未安装的可选 tokenizer 依赖都会返回客户端错误。
