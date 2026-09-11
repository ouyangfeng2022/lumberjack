# Splitter strategies

[中文](splitter-strategies.zh-CN.md)

Lumberjack supports Markdown, HTML, and DOCX through the same `DocTree` and
offers three structure-aware splitters plus a record splitter for flat inputs.
Every splitter respects `max_tokens` and uses the configured tokenizer for the
authoritative final chunk counts. This page is a decision guide: for each
choice it states when to use it, what the output looks like, and what you
trade away. Runnable end-to-end versions of these decisions live in
`examples/technical_document.py`, `examples/table_chunking.py`, and
`examples/incremental_counting.py`.

## Choosing a topology

| Strategy | Use it when | Trade-off |
| --- | --- | --- |
| `section` (default) | Each heading's body must stay coherent on its own — API references, FAQs, legal text. | Chunks fill less of the budget; no cross-section merging. |
| `sibling` | You want dense, well-filled chunks and small adjacent sections may share one chunk. | A chunk can span two sibling sections; per-section lookup is coarser. |
| `subtree` | Short nested sections belong together — tutorials with many small `###` under one `##`. | An entire subtree can occupy one chunk, so the deepest sections lose their own entry point. |
| `record` | Flat inputs with no real headings — CSV/TSV, JSONL, logs. | No heading context at all; complete records are never split. |

### `section` — one body per heading

```text
Input:                      Output chunks:
# Guide                     "# Guide / Intro + first paragraph"
## Intro                    "# Guide / Config + body"
## Config                   "# Guide / Advanced + body"
### Advanced
```

Use it when downstream consumers index or filter by heading and a chunk that
mixes two sections would confuse retrieval. The cost: a section ending at 90%
of the budget leaves the remaining 10% unused because the next section starts
a new chunk.

### `sibling` — pack adjacent siblings

```text
Input:                      Output chunks:
# Guide                     "# Guide / Intro + Config (merged, 95% of budget)"
## Intro (30 tok)           "# Guide / Advanced + body"
## Config (60 tok)
### Advanced
```

Use it for RAG pipelines that prefer fewer, denser chunks over strict
per-section boundaries. The trade-off: a retrieved chunk may contain the
neighbor section's text, and `merge_below_ratio` now works across sibling
boundaries (see below).

### `subtree` — keep whole branches

```text
Input:                      Output chunks:
# Guide                     "# Guide / Config subtree (### Advanced included, fits)"
## Config                   "# Guide / Usage subtree"
### Advanced
## Usage
```

Use it when a parent heading is meaningless without its children (a `##
Configuration` whose `###` children are each tiny). The trade-off: the whole
branch collapses into one chunk whenever it fits, so the `###` sections no
longer appear as separate retrieval units.

### `record` — no headings at all

```text
Input: CSV/JSONL/log         Output chunks:
row,row,row                  complete records packed up to max_tokens
```

Flat formats must not be forced through hierarchical splitters: their keys
would become fake headings and sibling merging would invent structure that
does not exist. Use `record` (or `--input-format csv`/`jsonl`/`log`, which the
CLI and web API select automatically). A single record larger than the budget
is emitted intact and marked `protected` instead of being split silently.

## Choosing a counting mode

| Mode | Names | Planning decisions | Use it when |
| --- | --- | --- | --- |
| incremental | unprefixed and `incremental-*` | running additive estimate | large corpora, hot paths — far fewer tokenizer calls |
| exact | `exact-*` | full recount of every rendered candidate | tight budgets, billing-grade token accounting |

Both modes emit identical `token_count` values: the finalizer always performs
the authoritative recount. They differ only in how the splitter *plans*:

- **Incremental** pre-measures the tree once and tracks a running estimate.
  Expect a small relative error at split time (visible in the Web UI and in
  `Chunk.estimated_token_count`), typically a few percent on mixed-language
  text with the `approx` tokenizer.
- **Exact** recounts every candidate, so split-time decisions match final
  counts exactly — at the cost of one tokenizer pass per decision.

Tokenizer choice is orthogonal: `--tokenizer tiktoken --splitter
incremental-sibling` is valid, and so is `--tokenizer approx --splitter
exact-section`. `examples/incremental_counting.py` measures both modes with
tokenizer call counts, wall time, and the estimate error.

## Tuning the budget knobs

### `ideal_max_tokens_ratio` (default `0.8`)

Splitters aim for `int(max_tokens * ratio)` before forcing a split, leaving
headroom so that heading context added at finalization does not push chunks
over budget. Lower it (e.g. `0.6`) when documents have very deep heading
paths or when the tokenizer is `approx` and you need a safety margin against
underestimation; raise it toward `1.0` when bodies are plain and chunks
underfill noticeably.

### `merge_below_ratio` (default `0.125`, `0` disables)

After splitting, a same-heading text tail smaller than
`int(max_tokens * ratio)` tokens is merged into its neighbor when the merged
result still fits. Set `merge_below_ratio=0` when chunk boundaries must be
predictable or reproducible for diffing — every paragraph then becomes its
own chunk even if it is 3 tokens long. Note that in the `section` splitter
merging only happens within one section's direct body, so `0` mainly changes
the `sibling` and `subtree` topologies.

### `heading_sensitive` (default `true`)

Controls whether the external heading path counts toward the split-time
budget. Set it to `false` when heading paths are extremely long (deeply nested
documentation) and you want the body to use the whole budget — the heading
tokens are then effectively free at planning time. This changes budget math
only: chunks still return `ancestor_headings`, `own_heading`, and the same
final `token_count` (which always includes the heading path), so retrieval
metadata never disappears.

## Oversized and protected blocks

Oversized fenced code falls back through paragraph breaks, line breaks,
sentences, words, and finally hard splits — but blocks explicitly configured
as unsplittable stay intact:

```python
from lumberjack.block import BlockConfig, BlockKind

# keep whole code fences even when they exceed max_tokens
block_options=[BlockConfig(kind=BlockKind.CODE_FENCE, split=False)]
```

Such a block is emitted as one chunk marked `protected=True` and exceeding
`max_tokens`. This is the correct trade-off when a broken code sample is worse
than an oversized chunk (tutorials, API docs). Treat `protected` chunks as a
signal for downstream handling rather than a budget violation: the benchmark
quality metrics account for them separately.

## Quick recipe

| Situation | Configuration |
| --- | --- |
| Default for headed documents | `section` |
| Dense chunks for vector search | `sibling`, `merge_below_ratio` at its default |
| Tiny nested sections that belong together | `subtree` |
| CSV / JSONL / logs | `record` |
| Strict, reproducible boundaries | any topology + `exact-*`, `merge_below_ratio=0` |
| Very large corpus | `incremental-*` (or unprefixed) + `approx` |
| Billing-grade accounting | `exact-*` + `tiktoken` |
