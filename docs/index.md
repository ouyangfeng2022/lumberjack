# Lumberjack documentation

Lumberjack turns Markdown, HTML, and DOCX into retrieval-ready chunks while
preserving document structure and heading context.

The Python pipeline returns a `SplitResult`: use `result.document` for parsed
document metadata and reference definitions, and `result.chunks` for the final
retrieval units.

Start with the [README](../README.md) for installation and a minimal Python
example. For choosing a splitting approach, see the
[splitter strategy guide](splitter-strategies.md).
