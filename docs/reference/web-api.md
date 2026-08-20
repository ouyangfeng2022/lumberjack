# Web API

[中文](../zh-CN/reference/web-api.md)

Install the Web extra and start the server:

```bash
pip install "lumberjack-py[web]"
lumberjack-serve --reload
```

The service publishes interactive OpenAPI documentation at [`http://127.0.0.1:9612/docs`](http://127.0.0.1:9612/docs) and an OpenAPI schema at [`http://127.0.0.1:9612/openapi.json`](http://127.0.0.1:9612/openapi.json).

## Endpoints

| Endpoint | Input |
| --- | --- |
| `POST /lumber/api/split/text` | JSON containing text-compatible formats and split options, including all supported code formats: Python, JavaScript/TypeScript, Bash, C/C++, C#, Go, Java, Kotlin, Lua, PHP, Ruby, Rust, Swift, and Zig. |
| `POST /lumber/api/split/file` | Multipart form with `file`, any supported `input_format`, and split options. XLSX requires `spreadsheets`; syntax-aware code parsing requires `code-parsing`. |

Both endpoints return `document`, `metadata`, `reference_definitions`, `chunk_count`, and serialized `chunks` matching the Python `Chunk` model.

Use `splitter: "record"` for LOG, CSV/TSV, JSON/JSONL, XML, and YAML inputs. It packs complete records and marks a single over-budget record as `protected` instead of splitting it.

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

The Web API uses the same default values and splitter names as the CLI. Invalid budget values, unsupported formats, and unavailable optional tokenizer dependencies return a client error.
