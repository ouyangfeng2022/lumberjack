# Pipeline and canonical rendering

[中文](../zh-CN/concepts/pipeline.md)

Lumberjack keeps input-specific parsing separate from format-neutral splitting:

```text
Document -> Parser.parse() -> DocTree -> Splitter.split() -> ChunkDraft[]
         -> ChunkFinalizer.finalize() -> TextNormalizer -> TextTransformer -> Chunk[]
```

| Stage | Responsibility |
| --- | --- |
| `Document` | Raw text, bytes, or a path plus format and caller-supplied provenance. |
| `Parser` | Converts Markdown, HTML, or DOCX into a `DocTree`. |
| `DocTree` | A heading tree of `SectionNode` values and canonical `DocumentBlock` content. |
| `Splitter` | Selects topology and produces unfinished `ChunkDraft` groups under a budget. |
| `ChunkFinalizer` | Renders drafts, applies post-processing, recounts tokens, and creates `Chunk` values. |

## Canonical rendering

`DocumentBlock.text` is the canonical rendered representation consumed by splitters. It is not necessarily a source slice: Markdown is normalized Markdown, while HTML and DOCX are converted to the same Markdown-like surface. This lets all splitters operate on every supported input format.

`DocTree.source` retains the original Markdown or HTML text. Binary parsers may leave it empty or use a normalized textual representation instead. Source line numbers are available where the parser can provide them; DOCX has no stable source line numbering.

## Post-processing stages

The default `TextNormalizer` only stabilizes line endings, BOM/NUL characters, and blank separators. The default `TextTransformer` keeps Markdown surface syntax. Use `PlainTextTransformer` only when your retrieval pipeline needs plain text rather than Markdown-like output.

The [custom components guide](../guides/custom-components.md) explains how to replace a stage without bypassing the rest of the pipeline.
