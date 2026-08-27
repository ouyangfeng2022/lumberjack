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
| `POST /lumber/api/split/text` | JSON：文本兼容的 `input_format` 与拆分选项，包含所有已支持的代码格式：Python、JavaScript/TypeScript、Bash、C/C++、C#、Go、Java、Kotlin、Lua、PHP、Ruby、Rust、Swift、Zig。 |
| `POST /lumber/api/split/file` | multipart form：`file`、任一已支持的 `input_format` 与拆分选项。XLSX 需要 `spreadsheets`；语法感知代码解析需要 `code-parsing`。 |

两个 endpoint 都会返回 `schema_version`（`lumberjack.chunk.v1`）、`document`、`metadata`、`reference_definitions`、`chunk_count`，以及与 Python `Chunk` model 对应的序列化 `chunks`。

LOG、CSV/TSV、JSON/JSONL、XML 和 YAML 输入请使用 `splitter: "record"`。它只打包完整记录；单条记录超过预算时会标记为 `protected`，不会拆开。

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

## 健康检查与版本

`GET /health`（等同 `GET /lumber/api/health`）返回 `{"status": "ok", "version": ...}`。
`GET /version`（等同 `GET /lumber/api/version`）在部署时设置了
`LUMBERJACK_BUILD_COMMIT` 环境变量的情况下会附带构建 commit。健康检查不消耗限流配额。

## 部署限制

公开部署内置资源限制，单个请求无法拖垮服务。通过环境变量配置（括号内为默认值）：

| 变量 | 含义 |
| --- | --- |
| `LUMBERJACK_WEB_MAX_BODY_BYTES` | 请求或上传的最大体积（5 MiB）。超出返回 `413`。 |
| `LUMBERJACK_WEB_MAX_CONCURRENT_SPLITS` | 并行执行的拆分数量；超出的请求排队等待（2）。 |
| `LUMBERJACK_WEB_SPLIT_TIMEOUT_SECONDS` | 单次拆分的墙钟时间预算；超出返回 `503`（30）。 |
| `LUMBERJACK_WEB_RATE_LIMIT_REQUESTS` | 每客户端每窗口的 API 请求数；超出返回 `429`（60）。 |
| `LUMBERJACK_WEB_RATE_LIMIT_WINDOW_SECONDS` | 限流窗口长度（60）。 |

限流只作用于拆分 API，不影响健康检查和静态资源。非法取值会在启动时立刻报错，而不是被静默忽略。

## 隐私

上传与粘贴的文本只在内存中处理：不落盘、不存储、不转发到任何地方。服务不会访问用户提供的
URL——只读取请求本身。请求日志仅包含 HTTP 方法、路径、状态码和耗时，绝不包含文档内容或参数。
错误信息经过脱敏，不会泄露服务器文件路径。
