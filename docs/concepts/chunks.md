# Chunks and provenance

[中文](../zh-CN/concepts/chunks.md)

`Chunk` keeps retrieval content and section context as separate fields:

| Field | Meaning |
| --- | --- |
| `body` | Rendered chunk body. External headings are not rendered here. Headings for internal merged sections remain part of the body. |
| `ancestor_headings` | Heading path above the chunk's own section. |
| `own_heading` | The chunk's own `(level, title)` pair, or `None` when a chunk represents multiple merged sibling sections. |
| `token_count` | Authoritative final count: headings, their separator, and body after finalization. |
| `estimated_token_count` | The split-time estimate. It may differ slightly when incremental planning was used. |
| `headings_token_count` / `body_token_count` | The two components of the final count. |
| `start_line` / `end_line` | One-based source positions when the parser can determine them. |
| `document_title` / `document_path` | Source document identity and provenance. |

The heading path is canonical Markdown rendering. When `heading_sensitive=True`, the splitter includes the rendered heading path and the blank separator before the body in the budget. The metadata is returned regardless of that setting.

`SplitResult.document` retains document-level metadata and Markdown reference definitions. Use this data to link an indexed chunk back to its source, but do not assume line ranges exist for binary inputs such as DOCX.
