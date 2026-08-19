# CLI reference

[中文](../zh-CN/reference/cli.md)

`lumber` reads one Markdown, HTML, or DOCX file and emits a JSON object to standard output. Use `--output` to write that JSON to a file instead.

```bash
lumber INPUT [OPTIONS]
```

| Option | Default | Meaning |
| --- | --- | --- |
| `--input-format` | `auto` | `auto`, `markdown`, `html`, or `docx`. Auto detects a file extension. |
| `--tokenizer` | `approx` | `approx`, `tiktoken`, or `transformers`; controls encoding and token counting only. |
| `--splitter` | `sibling` | Structure topology and counting mode. See [splitting](../concepts/splitting.md). |
| `--max-tokens` | `1200` | Maximum tokens per chunk. |
| `--ideal-max-tokens-ratio` | `0.8` | Preferred split budget divided by `max_tokens`. |
| `--merge-below-ratio` | `0.125` | Same-heading tail merge threshold in `[0.0, 1.0)`; `0` disables it. |
| `--[no-]heading-sensitive` | enabled | Include external heading-path tokens in split budgets. Heading metadata is always returned. |
| `--max-heading-level` | unset | Deepest heading level retained as section context. |
| `--block-config` | repeatable | Per-block policy: `KIND[:isolated][:nosplit][:TOKENS]`. |
| `--block-config-json` | unset | Structured JSON policy; overrides matching `--block-config` values. |
| `-o`, `--output` | stdout | Output file path. |

For example:

```bash
lumber handbook.md \
  --max-tokens 800 \
  --tokenizer tiktoken \
  --splitter incremental-sibling \
  --block-config table:500:nosplit:isolated
```

Run `lumber --help` for the CLI's generated help text. The documentation build and CLI contract tests ensure this reference stays aligned with its public options.
