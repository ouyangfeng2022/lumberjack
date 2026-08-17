# Splitter strategies

Lumberjack supports Markdown, HTML, and DOCX through the same `DocTree` and
offers three structure-aware splitters. Each splitter respects `max_tokens` and
uses the configured tokenizer for final chunk counts.

| Strategy | Use it when |
| --- | --- |
| `sibling` (default) | You want well-filled chunks and can pack adjacent sibling sections with shared context. |
| `subtree` | You prefer to retain an entire section subtree whenever it fits the budget. |
| `section` | You need each section's direct body handled independently. |

## Counting modes

The unprefixed names use incremental estimates while planning, followed by an
authoritative final count. Use `exact-sibling`, `exact-subtree`, or
`exact-section` when every planning decision must fully recount rendered text.
The explicit `incremental-*` names are equivalent to their unprefixed forms.

Tokenizer choice and counting mode are independent: for example,
`--tokenizer tiktoken --splitter incremental-sibling` is valid.

## Context and budget behavior

Chunks retain `ancestor_headings` and `own_heading` as metadata. The
`heading_sensitive` option controls whether external heading-path tokens count
toward the splitter's budget; it does not remove the returned heading metadata.
Budget calculations include the tokenized blank-line separator between the
external heading path and body, matching final chunk counts.

Oversized text falls back from paragraph breaks to line breaks, sentences,
words, and finally hard splits. Fenced code blocks remain intact by default.
Explicitly non-splittable blocks and protected URL spans may exceed the budget.
The default `merge_below_ratio` of `0.125` lets the sibling and subtree
splitters merge a small same-heading text tail when the merged result fits; set
it to `0` to disable this behavior. The section splitter does not collapse
subtrees or merge across sections.
