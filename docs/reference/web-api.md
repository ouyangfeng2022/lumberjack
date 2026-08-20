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
| `POST /lumber/api/split/text` | JSON containing `text` and `input_format` (`markdown`, `html`, `text`, `log`, `csv`, `tsv`, or `jsonl`) plus split options. |
| `POST /lumber/api/split/file` | Multipart form with `file`, `input_format` (`auto`, `markdown`, `html`, `docx`, `text`, `log`, `csv`, `tsv`, or `jsonl`), plus split options. |

Both endpoints return `document`, `metadata`, `reference_definitions`, `chunk_count`, and serialized `chunks` matching the Python `Chunk` model.

Use `splitter: "record"` for LOG, CSV/TSV, and JSONL inputs. It packs complete records and marks a single over-budget record as `protected` instead of splitting it.

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
