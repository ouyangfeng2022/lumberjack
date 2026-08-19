# Lumberjack documentation

[中文](zh-CN/index.md)

Lumberjack turns Markdown, HTML, and DOCX into retrieval-ready chunks while preserving document structure and heading context. Start with the [installation guide](getting-started/installation.md), then split your first document in the [quickstart](getting-started/quickstart.md).

## What makes a chunk useful for retrieval?

Lumberjack separates a chunk's body from its heading path, tracks source provenance, and respects document blocks while applying a configurable token budget. One format-neutral `DocTree` supports all built-in parser formats and all splitter strategies.

| I want to… | Start here |
| --- | --- |
| Choose a strategy or counting mode | [Splitting and counting](concepts/splitting.md) |
| Understand output fields and source locations | [Chunks and provenance](concepts/chunks.md) |
| Configure code/table behavior | [Configuration](guides/configuration.md) |
| Extend the pipeline | [Custom components](guides/custom-components.md) |
| Call the CLI or Web API | [Reference](reference/cli.md) |

The project is still building its benchmark suite. This site does not make unverified performance or quality claims.
