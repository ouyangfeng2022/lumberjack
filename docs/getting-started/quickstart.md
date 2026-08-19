# Quickstart

[中文](../zh-CN/getting-started/quickstart.md)

The default pipeline accepts a string, bytes, or a `pathlib.Path`. A plain string is always document content, never a filesystem path.

```python
from pathlib import Path

from lumberjack import Lumberjack

jack = Lumberjack(max_tokens=1200)
result = jack.saw(Path("handbook.md"))

for chunk in result.chunks:
    print({"heading": chunk.own_heading, "body": chunk.body, "tokens": chunk.token_count})
```

`Lumberjack.saw()` returns a `SplitResult`. Its `document` is the parsed `DocTree`; its `chunks` are final `Chunk` values ready for indexing.

## Choose an input format

`format="auto"` is the default. With a `Path`, it selects Markdown, HTML, or DOCX by extension. Override it when the source does not have a useful name:

```python
html = "<h1>Release notes</h1><p>Ship the package.</p>"
result = Lumberjack(max_tokens=300).saw(html, format="html")
```

DOCX input requires the `docx` extra and uses bytes or a path:

```python
result = Lumberjack(max_tokens=800).saw(Path("report.docx"), format="docx")
```

## Inspect the output

The headings are metadata, separate from the body. This makes it possible to use the body for embedding while retaining the context for retrieval or display.

```python
chunk = result.chunks[0]
print(chunk.ancestor_headings)
print(chunk.own_heading)
print(chunk.body)
print(chunk.token_count)
```

Read [Chunks and provenance](../concepts/chunks.md) for complete field semantics, or use the [CLI](../reference/cli.md) when your workflow already starts with files.
