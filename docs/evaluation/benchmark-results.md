# Benchmark methodology

Lumberjack does not make performance or quality claims without a linked,
repeatable report. The benchmark MVP records structured quality, token-budget
accuracy, and performance samples for a public CC0 corpus.

Run it from the repository root:

```bash
uv run python -m benchmarks.run --adapter lumberjack --splitter section
```

The run performs one warmup and five measured repetitions per document by
default. It writes `raw.json` and `summary.json` under
`benchmarks/results/<date>-<commit>/`. `raw.json` contains the complete
configuration, commit, Python/platform information, individual timing samples,
and chunks; no report should be based on a single invocation.

## Metrics

| Metric | Meaning |
| --- | --- |
| `content_recall` | Fraction of dataset-annotated required content found in output chunks. |
| `duplication_rate` | Repeated non-intentional chunk payloads divided by total chunks. |
| `budget_violation_rate` | Non-protected chunks above `max_tokens`; oversized protected blocks are excluded. |
| `block_break_rate` | Protected dataset blocks not represented in exactly one chunk. |
| `chunk_utilization` | Used budget across non-protected chunks. |
| `estimate_error` | Mean relative difference between estimated and final token counts. |
| `provenance_coverage` | Chunks carrying both source line bounds. |
| `token_p50` / `token_p95` | Token-count distribution of emitted chunks. |

Performance measurements include wall-clock time, CPU time, Python allocation
peak, throughput per MB, and tokenizer `count`/`encode` calls. The report
stores median, P95, standard deviation, and every raw sample.

## Comparability

An adapter must report its equivalent configuration in the generated report.
When a tool cannot preserve headings, protected blocks, or provenance, that is
an explicit comparability limitation—not a missing value hidden from results.
Competitor packages are optional benchmark dependencies and never core package
dependencies.

The checked-in corpus provides five CC0 documents per scenario plus three
cross-format Markdown/HTML equivalence groups. It is sized for repeatable
harness validation, not for headline numbers. Publish an outcome only after
running the corpus on the commit being discussed and linking its exact result
directory here. The first published baseline follows.

## Published baseline — 2026-09-03

Measured on commit `5e60b30b6925` with the full adapter set: the two lumberjack
counting modes plus nine competitor variants. Results live in
`benchmarks/results/20260903-5e60b30b6925/` (regenerate with the commands
below); the aggregator `benchmarks/compare.py` produced `summary.json` and
`comparison.md` from the per-run `raw.json` files and exits non-zero when a
native oracle fails.

### Environment

| Item | Value |
| --- | --- |
| Commit | `5e60b30b6925` (`dev`) |
| Date | 2026-09-03 |
| OS / CPU | Linux (WSL2), AMD Ryzen 7 5800H, 8 threads |
| Python | 3.12.3 |
| Lumberjack stack | markdown-it-py 4.0.0, tiktoken 0.12.0 |
| Competitors | langchain-text-splitters 1.1.2, unstructured 0.25.2, docling 2.120.3 (docling-core 2.91.0), chonkie 1.7.0 |
| Dataset | `2026.08.27` — 36 documents, six scenarios + three cross-format pairs (~33 KB total) |
| Config | `max_tokens=240`, 1 warmup, 5 repetitions; token unit = UTF-8 bytes ÷ 3 |

Budget equivalence: `langchain-recursive` uses a byte/3 length function with
`chunk_size=240`; both chonkie chunkers use the byte-counting `ByteTokenizer`
with `chunk_size=720` bytes; `docling-hybrid` uses an offline byte/3
`BaseTokenizer` whose `get_max_tokens()` returns 240. `langchain-markdown` /
`langchain-html` are header splitters with no budget parameter, and
`docling-hierarchical` has no budget parameter by design — their violations are
the tools' genuine behavior under an equal budget requirement.

### Quality (mean across 36 documents)

| Run | Content recall | Budget violations | Block breaks | Duplication | Utilization | Chunks | Token p50 / p95 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| `lumberjack` (section, incremental) | 1.000 | 0.000 | 0.000 | 0.000 | 0.277 | 194 | 49 / 162 |
| `lumberjack` (exact-section) | 1.000 | 0.000 | 0.000 | 0.000 | 0.277 | 194 | 49 / 162 |
| `langchain-recursive` | 1.000 | 0.000 | 0.000 | 0.000 | 0.646 | 67 | 173 / 226 |
| `langchain-markdown` | 1.000 | 0.083 | 0.000 | 0.000 | 0.354 | 165 | 44 / 186 |
| `langchain-html` | 1.000 | 0.611 | 0.000 | 0.000 | 0.761 | 67 | 54 / 516 |
| `unstructured-basic` | 0.986 | 0.000 | 0.028 | 0.003 | 0.111 | 433 | 8 / 84 |
| `unstructured-by-title` | 0.986 | 0.000 | 0.028 | 0.000 | 0.403 | 117 | 62 / 166 |
| `docling-hierarchical` | 0.153 | 0.013 | 0.028 | 0.000 | 0.252 | 200 | 31 / 170 |
| `docling-hybrid` | 0.153 | 0.000 | 0.028 | 0.000 | 0.274 | 190 | 34 / 173 |
| `chonkie-recursive` | 1.000 | 0.000 | 0.000 | 0.000 | 0.656 | 66 | 172 / 236 |
| `chonkie-table` | 0.597 | 0.125 | 0.000 | 0.000 | 0.449 | 42 | 209 / 333 |

Only the lumberjack runs emit every chunk with both source line bounds
(`provenance_coverage` 1.0); no competitor adapter emits line provenance, so
that column is not comparable and is omitted here.

### Performance (medians over 5 repetitions)

| Run | Total wall (36 docs) | Mean per doc | Throughput | Peak alloc | Count calls |
| --- | ---: | ---: | ---: | ---: | ---: |
| `lumberjack` (section, incremental) | 0.183 s | 5.1 ms | 0.181 MB/s | 0.5 MB | 1878 |
| `lumberjack` (exact-section) | 0.189 s | 5.2 ms | 0.175 MB/s | 0.5 MB | 487 |
| `lumberjack` (section, tiktoken) | 0.211 s | 5.9 ms | 0.157 MB/s | 0.5 MB | 1845 |
| `lumberjack` (exact-section, tiktoken) | 0.191 s | 5.3 ms | 0.173 MB/s | 0.5 MB | 466 |
| `langchain-recursive` | 0.003 s | 0.1 ms | 9.495 MB/s | 0.0 MB | 0 |
| `langchain-markdown` | 0.014 s | 0.4 ms | 2.373 MB/s | 0.0 MB | 0 |
| `langchain-html` | 0.023 s | 0.6 ms | 1.460 MB/s | 0.1 MB | 0 |
| `unstructured-basic` | 0.541 s | 15.0 ms | 0.061 MB/s | 0.2 MB | 0 |
| `unstructured-by-title` | 0.602 s | 16.7 ms | 0.055 MB/s | 0.2 MB | 0 |
| `docling-hierarchical` | 9.670 s | 268.6 ms | 0.003 MB/s | 0.5 MB | 0 |
| `docling-hybrid` | 9.993 s | 277.6 ms | 0.003 MB/s | 0.5 MB | 0 |
| `chonkie-recursive` | 0.008 s | 0.2 ms | 4.370 MB/s | 0.0 MB | 0 |
| `chonkie-table` | 0.005 s | 0.1 ms | 6.589 MB/s | 0.0 MB | 0 |

The docling runs are dominated by document conversion, not chunking; treat
their wall time as conversion cost on 36 small documents, not as a chunker
speed verdict. `count_calls` counts lumberjack tokenizer invocations only.

### Counting modes (lumberjack only)

Exact and incremental counting emitted identical chunk sets under both
tokenizers (194 chunks with `approx`, 190 with `tiktoken`). Incremental
estimates were within rounding distance of the final counts on this corpus:
mean relative error 0.00013 under `approx`, and exactly zero deviation on all
190 chunks under `tiktoken`. At larger scale the randomized splitter benchmark
(`benchmarks/splitter_random_run.py`) measures a mean absolute estimate error
of 0.003 tokens and a maximum of 2.0 tokens under `tiktoken`. Exact counting
needed fewer tokenizer `count` calls on this corpus (487 vs 1878 under
`approx`; 466 vs 1845 under `tiktoken`) at comparable wall time.

### Findings

1. **Structure-aware budget packing is the only entrant holding all five
   invariants.** Both lumberjack counting modes score content recall 1.0 with
   zero budget violations, zero duplicated payloads, zero broken protected
   blocks, and full source-line provenance. Every competitor trades away at
   least one of these on the same corpus and budget.
2. **Window packers reach higher utilization but emit no structure.**
   `langchain-recursive` and `chonkie-recursive` pack tight windows
   (utilization 0.646 / 0.656) without violations on this corpus, but their
   chunks carry no heading context, no provenance, and boundaries follow
   separators, not document structure. Lumberjack keeps headings and atomic
   tables/code intact, which at `max_tokens=240` yields more, smaller chunks
   (utilization 0.277) — the deliberate price of never breaking a protected
   block.
3. **Docling keeps headings in metadata, not chunk text.** All 61 recall
   misses across the docling runs are heading strings or raw Markdown
   table-header signatures; no body prose was lost (verified per document).
   `docling-hybrid` respects the translated budget; `docling-hierarchical`
   has no budget parameter and 1.3% of its structure chunks exceed it.
4. **Header splitters without budgets overflow on long sections.**
   `langchain-markdown` preserves headings but 8.3% of chunks exceed the
   budget; `langchain-html` applies to HTML inputs only — on the Markdown
   majority of this corpus it degrades to whole-document chunks (61.1%
   violations).
5. **Element-level splitting fragments documents.** `unstructured-basic`
   emits 433 chunks with an 8-token median (utilization 0.111) and splits
   protected blocks across elements (2.8%); `unstructured-by-title` improves
   packing (0.403) with the same protected-block breaks.
6. **`chonkie-table` is table-specialized.** It scores perfect recall in the
   tables scenario but drops heading text elsewhere (0.597 overall recall —
   all misses are headings, no prose) and 12.5% of chunks exceed the budget
   from merged rows.
7. **Counting mode is a cost dial, not a quality dial.** On this corpus both
   modes emit identical chunks; incremental estimation is essentially exact
   (error ≤ 2 tokens at scale), while exact counting trades fewer tokenizer
   calls for full recounts.

### Known non-comparabilities

- No competitor adapter emits source-line provenance; `provenance_coverage`
  is reported as 0 with a diagnostic and excluded from conclusions.
- The token unit is UTF-8 bytes ÷ 3 for every entrant; budgets were translated
  per tool as described above. BPE tokenizers used in production will shift
  absolute token counts, not relative behavior.
- Dataset annotations include heading strings and raw table-header rows;
  tools that keep headings in metadata (docling) or drop headings
  (chonkie-table) are penalized by `content_recall` on those items — the
  per-item misses are published above so the penalty is auditable.
- One machine, one warm process per adapter, medians of five repetitions.
  The corpus (~33 KB, 36 documents) is designed for repeatable harness
  validation; scale conclusions require the randomized splitter benchmark.

### Reproduction

```bash
uv sync --group dev --group test --group benchmark \
  --extra tokenizers --extra docx --extra web
BASE="benchmarks/results/$(date +%Y%m%d)-$(git rev-parse --short=12 HEAD)"
uv run python -m benchmarks.run --adapter lumberjack --splitter section \
  --output "$BASE/lumberjack"
uv run python -m benchmarks.run --adapter lumberjack --splitter exact-section \
  --output "$BASE/lumberjack-exact-section"
uv run python -m benchmarks.run --adapter lumberjack --splitter section \
  --tokenizer tiktoken --output "$BASE/lumberjack-tiktoken"
uv run python -m benchmarks.run --adapter lumberjack --splitter exact-section \
  --tokenizer tiktoken --output "$BASE/lumberjack-exact-section-tiktoken"
for adapter in langchain-recursive langchain-markdown langchain-html \
  unstructured-basic unstructured-by-title docling-hierarchical \
  docling-hybrid chonkie-recursive chonkie-table; do
  uv run python -m benchmarks.run --adapter "$adapter" --output "$BASE/$adapter"
done
uv run python -m benchmarks.compare "$BASE"
```
