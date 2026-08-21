# CLI reference

[中文](../zh-CN/reference/cli.md)

`lumber` reads one supported document file and emits a versioned JSON object to
standard output. Use `--output` to write that JSON to a file instead. A directory
or glob is processed as ordered JSONL records, one success or failure outcome per
input; progress and errors always go to stderr.

```bash
lumber INPUT [OPTIONS]
```

| Option | Default | Meaning |
| --- | --- | --- |
| `--input-format` | `auto` | All documented input formats, including `sql`, `sqlite`, `notebook`, and code formats: `python`, `javascript`, `typescript`, `bash`, `c`, `cpp`, `csharp`, `go`, `java`, `kotlin`, `lua`, `php`, `ruby`, `rust`, `swift`, and `zig`. Auto detects supported file extensions. Syntax-aware code parsing requires `code-parsing`. |
| `--tokenizer` | `approx` | `approx`, `tiktoken`, or `transformers`; controls encoding and token counting only. |
| `--splitter` | `section` | Structure topology and counting mode. Use `record` for LOG, CSV/TSV, JSON/JSONL, XML, and YAML so input records remain atomic. See [splitting](../concepts/splitting.md). |
| `--max-tokens` | `1200` | Maximum tokens per chunk. |
| `--ideal-max-tokens-ratio` | `0.8` | Preferred split budget divided by `max_tokens`. |
| `--merge-below-ratio` | `0.125` | Same-heading tail merge threshold in `[0.0, 1.0)`; `0` disables it. |
| `--[no-]heading-sensitive` | enabled | Include external heading-path tokens in split budgets. Heading metadata is always returned. |
| `--max-heading-level` | unset | Deepest heading level retained as section context. |
| `--block.<kind>.isolated` | unset | Set whether a block kind must form its own chunk: `true` or `false`. |
| `--block.<kind>.split` | unset | Set whether an oversized block kind may be split: `true` or `false`. |
| `--block.<kind>.max-tokens` | unset | Set a positive per-kind token budget. |
| `--block.table.repeat-header`, `--block.html_table.repeat-header` | unset | Set whether split Markdown or HTML tables repeat their header: `true` or `false`. |
| `-o`, `--output` | stdout | Output file path. |
| `--output-dir` | unset | Write one per-input JSON record; existing files require `--overwrite`. |
| `--recursive` | disabled | Recurse when the input is a directory. |
| `--jsonl` | disabled | Emit JSONL even for one input. |
| `--fail-fast` | disabled | Stop on the first input failure. |

`<kind>` is one of `paragraph`, `blockquote`, `list`, `list_item`, `table`,
`html_table`, `code_block`, `code_fence`, `html_block`, `front_matter`,
`math_block`, or `math_block_eqno`. Repeat an option when necessary; the final
value wins.

For example:

```bash
# One document.
lumber handbook.md \
  --max-tokens 800 \
  --tokenizer tiktoken \
  --splitter incremental-sibling \
  --block.table.max-tokens 500 \
  --block.table.split false \
  --block.table.isolated true

# Stream a directory safely into a pipeline.
lumber data/ --recursive | jq -c 'select(.status == "success")'

# Preserve one result per input without overwriting earlier output by accident.
lumber 'data/**/*.md' --recursive --output-dir chunks/
```

Run `lumber --help` for the CLI's generated help text. The documentation build and CLI contract tests ensure this reference stays aligned with its public options.
