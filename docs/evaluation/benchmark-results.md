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
directory here.
