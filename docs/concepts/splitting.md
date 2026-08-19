# Splitting and counting

[中文](../zh-CN/concepts/splitting.md)

Every splitter consumes the same `DocTree`, but it chooses a different document topology before applying token budgets.

| Splitter | Topology |
| --- | --- |
| `SiblingSplitter` / `sibling` | Packs adjacent sibling sections that fit, retaining their shared context. |
| `SubtreeSplitter` / `subtree` | Keeps a complete section subtree intact whenever it fits, then falls back within the section. |
| `SectionSplitter` / `section` | Processes each section's direct body independently; it does not collapse subtrees. This is the default. |

## Exact and incremental planning

The unprefixed classes and integration names use incremental counting. They keep a running additive estimate while deciding whether to pack content, then `ChunkFinalizer` performs the authoritative final count. The explicit `incremental-*` integration names are equivalent.

`ExactSiblingSplitter`, `ExactSubtreeSplitter`, and `ExactSectionSplitter` fully recount each rendered candidate at planning time. Use their `exact-*` CLI and Web API names when planning precision matters more than speed.

This is independent of the tokenizer engine. `approx` estimates tokens from UTF-8 byte length; `tiktoken` and `transformers` require the `tokenizers` extra. Any tokenizer works with either counting mode.

## Budget controls

- `max_tokens` is the maximum target budget.
- `ideal_max_tokens_ratio` (default `0.8`) is the preferred budget used while deciding where to split; it must be greater than zero and no more than one.
- `merge_below_ratio` (default `0.125`) merges a small same-heading text tail into the preceding chunk when the result fits. Set it to `0` to disable the behavior. It applies to sibling and subtree splitters, not across section bodies.
- `heading_sensitive=True` (the default) includes external heading-path tokens in split budgets. It does not remove headings from returned metadata.
- `max_heading_level` limits which headings are retained as section context; deeper headings are rendered as body text.

## Oversized blocks and tables

Oversized text falls back in this order: paragraph breaks, line breaks, sentences, words, then hard splitting. Fenced code blocks remain intact by default unless their block policy enables splitting. A protected URL span or an explicit non-splittable block may therefore exceed `max_tokens`.

Markdown and HTML tables can repeat their header row on each split piece. See [configuration](../guides/configuration.md) for typed table policies.
