# HTML Parser Organization Design

## Goal

Reorganize `src/lumberjack/core/html_parser.py` into an `html/` package so that
HTML sits at the same layer and follows the same shape as the `markdown/` and
`docx/` format packages. The project is in active development, so the old flat
module does not need a compatibility shim. This refactor must preserve behavior.

## Current Shape

`src/lumberjack/core/html_parser.py` is a single ~850-line file that mixes two
unrelated concerns that do not call each other:

- **Document parser**: `HTMLParser` and its private `_HTMLDocumentBuilder`
  (plus private helpers `_clean_text`, `_line_offsets`, `_attrs_dict`,
  `_TextCollector`, `_ListItem`, `_ListCollector`, `_TableCollector`). This is
  the direct analog of `MarkdownItParser` and `DocxParser`. It produces a
  heading-tree `DocumentAST`. It emits `html_table` blocks itself via an
  internal `_table_stack` and never calls `HTMLTableParser`.
- **Table extraction utility**: `HTMLTableParser` and its dataclasses
  `HTMLTable`, `HTMLTableRow`, `HTMLTableCell`. These are block-handling
  helpers consumed by:
  - `src/lumberjack/core/markdown/parser.py:670` — to detect a `<table>` inside
    a Markdown `html_block` and re-tag it as `html_table`.
  - `src/lumberjack/core/text_splitter.py:10` — to split oversized `html_table`
    blocks.

Because the two groups share no code, the only real design decision is where
the table utility lives. The agreed placement is inside the new `html/` package
(see Decision below).

The other format packages already follow a consistent shape:

```text
src/lumberjack/core/markdown/
    __init__.py          # re-exports MarkdownItParser, MarkdownParser
    parser.py            # MarkdownItParser
src/lumberjack/core/docx/
    __init__.py          # re-exports DocxParser
    parser.py            # DocxParser
```

HTML should match.

## Target Structure

Create a new package:

```text
src/lumberjack/core/html/
    __init__.py          # re-export HTMLParser only
    parser.py            # HTMLParser + _HTMLDocumentBuilder + private helpers
    table_parser.py      # HTMLTableParser + HTMLTable/HTMLTableRow/HTMLTableCell
```

Responsibilities:

- `parser.py`: `HTMLParser`, `_HTMLDocumentBuilder`, and the private helpers
  `_clean_text`, `_line_offsets`, `_attrs_dict`, `_TextCollector`, `_ListItem`,
  `_ListCollector`, `_TableCollector` that are used only by the document
  builder.
- `table_parser.py`: `HTMLTableParser` and the `HTMLTable`, `HTMLTableRow`,
  `HTMLTableCell` frozen dataclasses.
- `__init__.py`: public package export. Re-export only `HTMLParser`, mirroring
  `markdown/__init__.py` and `docx/__init__.py`, whose package entry points
  expose only the format's document parser.

Remove the old `src/lumberjack/core/html_parser.py` after all imports are
migrated.

## Decision: Table Parser Placement

`HTMLTableParser` and its dataclasses go into the new `html/` package as
`table_parser.py`, rather than staying in a core-level shared module. Reasoning:

- The table utility parses HTML table syntax; it is naturally HTML code.
- Keeping all HTML-related code in one package matches the goal of putting HTML
  on equal footing with the `markdown/` and `docx/` format packages.
- Consumers import it via the explicit submodule path
  `lumberjack.core.html.table_parser`, which signals that it is a block
  utility, not the format's document parser.

## Import Policy

Preferred public import for the document parser:

```python
from lumberjack.core.html import HTMLParser
```

Table utility consumers use the explicit submodule:

```python
from lumberjack.core.html.table_parser import HTMLTableParser, HTMLTableRow
```

Internal modules within `core/` use relative imports equivalent to the above.

## Import Migration

Three import sites reference the old flat module. All are mechanical changes:

```python
# src/lumberjack/core/markdown/parser.py (currently line ~670)
- from ..html_parser import HTMLTableParser
+ from ..html.table_parser import HTMLTableParser
```

```python
# src/lumberjack/core/text_splitter.py (currently line ~10)
- from .html_parser import HTMLTableParser, HTMLTableRow
+ from .html.table_parser import HTMLTableParser, HTMLTableRow
```

```python
# tests/test_html_parser.py (currently lines ~5-7)
- from lumberjack.core.html_parser import (
-     HTMLParser,
-     HTMLTableParser,
- )
+ from lumberjack.core.html import HTMLParser
+ from lumberjack.core.html.table_parser import HTMLTableParser
```

`tests/test_html_table_integration.py` exercises HTML-table splitting through
the public pipeline and does not import `html_parser` symbols directly, so it
needs no import change.

`src/lumberjack/core/__init__.py` currently does not re-export any HTML
symbols and will not after this refactor.

A grep for `html_parser`, `HTMLParser`, `HTMLTableParser`, `HTMLTable`,
`HTMLTableRow`, and `HTMLTableCell` across `src/` and `tests/` confirms there
are no other references to migrate.

## Behavior Constraints

This is a structural refactor only.

- Do not change the `DocumentAST` shape produced by `HTMLParser`.
- Do not change `HTMLTableParser` behavior or the `HTMLTable*` dataclass
  fields.
- Do not change public names: `HTMLParser`, `HTMLTableParser`, `HTMLTable`,
  `HTMLTableRow`, `HTMLTableCell`.
- Do not move `html_table` block splitting out of `text_splitter.py`. That is
  oversized-block fallback handling and stays in `core/text_splitter.py`,
  consistent with the splitter-organization design which keeps `TextSplitter`
  out of the splitter package.
- Do not add HTML re-exports to `src/lumberjack/core/__init__.py`.

## Documentation Updates

Update references to the old flat module in project documentation:

- `AGENTS.md` — add an `### HTML` subsection under `Architecture` describing
  the new `core/html/` package, parallel to the existing Markdown and DOCX
  subsections. Keep `core/text_splitter.py` documented as the oversized-block
  fallback that consumes `HTMLTableParser`.
- `README.md` / `README.zh-CN.md` only if they mention the old module path.

Grep for `html_parser`, `core/html_parser`, and `HTMLParser` across docs and
update any matches.

## Testing

Run focused HTML tests first, then the broader Python checks:

```bash
uv run pytest tests/test_html_parser.py tests/test_html_table_integration.py -q
uv run ruff check --fix
uv run ruff format
uv run ruff check
uv run pytest -q
```

The existing HTML and table-integration tests are the behavior safety net. If
the pre-existing deletion of
`tests/fixtures/markdown/deep-research-report.md` causes an unrelated failure
in the full suite, record it and do not restore the fixture.

## Risks

- The main risk is missing a stale import of `lumberjack.core.html_parser`. Use
  `rg` to find and migrate all references before deleting the old module.
- The second risk is the `HTMLParser` class name shadowing the stdlib
  `html.parser.HTMLParser`. This is already handled: the document builder
  aliases the stdlib class to `_StdlibHTMLParser` and subclasses it; the public
  class is `HTMLParser`. Keep that alias in `parser.py` after the move.
