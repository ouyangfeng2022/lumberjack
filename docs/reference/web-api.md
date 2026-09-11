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

Both endpoints return `schema_version` (`lumberjack.chunk.v1`), `document`,
`metadata`, `reference_definitions`, `chunk_count`, and serialized `chunks`
matching the Python `Chunk` model.

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

## Health and version

`GET /health` (also `GET /lumber/api/health`) returns `{"status": "ok", "version": ...}`.
`GET /version` (also `GET /lumber/api/version`) adds the build commit when the
`LUMBERJACK_BUILD_COMMIT` environment variable is set at deploy time. Health
probes are exempt from rate limiting.

## Deployment limits

Public deployments enforce resource limits so one request cannot exhaust the
server. Configure them with environment variables (defaults in parentheses):

| Variable | Meaning |
| --- | --- |
| `LUMBERJACK_WEB_MAX_BODY_BYTES` | Maximum request or upload size (5 MiB). Larger requests get `413`. |
| `LUMBERJACK_WEB_MAX_CONCURRENT_SPLITS` | Splits running in parallel; further requests queue (2). |
| `LUMBERJACK_WEB_SPLIT_TIMEOUT_SECONDS` | Wall-clock budget per split; exceeded requests get `503` (30). |
| `LUMBERJACK_WEB_RATE_LIMIT_REQUESTS` | API requests per client per window; exceeded requests get `429` (60). |
| `LUMBERJACK_WEB_RATE_LIMIT_WINDOW_SECONDS` | Rate-limit window length (60). |

Rate limiting applies only to the split API, not to health probes or static
assets. Invalid values fail loudly at startup instead of being ignored.

## Privacy

Uploads and pasted text are processed in memory only: nothing is written to
disk, and documents are never stored or forwarded anywhere. The server does not
fetch URLs supplied by users — it only reads the request body you send. Request
logs contain the HTTP method, path, status code, and duration, but never any
document content or parameters. Error messages are sanitized so they cannot
leak server file paths.
