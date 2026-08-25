# Parser coverage and robustness

This page defines what “parsed successfully” means for Lumberjack. A file that
does not raise an exception is only the first level of validation. Parser
quality is evaluated at three independent levels:

1. **Package/tree validity:** parsing completes and the resulting `DocTree`
   satisfies hierarchy, source-range, and non-empty-block invariants.
2. **Content retention:** lexical-token recall and non-whitespace-character
   recall compare visible source content with the parsed tree. DOCX character
   recall is the reliable fallback when producer-specific run boundaries split
   or join words differently.
3. **Element conformance:** versioned cases assert required and forbidden
   section, block, and inline kinds. This catches a parser that retains text but
   classifies an equation, link, table, or code span incorrectly.

The corpus benchmark is a regression baseline, not a proof that every possible
document is supported.

## Markdown dialect

The default parser is GFM-like Markdown from `markdown-it-py`, with YAML front
matter and Lumberjack math extensions. CommonMark itself does not define math,
so the math rules below are Lumberjack's explicit dialect contract.

| Input element | Representation | Current behavior |
| --- | --- | --- |
| ATX headings | `SectionNode` | H1-H6 hierarchy and heading inlines |
| Setext headings | `SectionNode` | Disabled by default; enable with `disable_lheading=False` |
| Paragraphs | `paragraph` | Inline structure and source line range retained |
| Emphasis/strong/strike | inline nodes | Nested content retained |
| Code span | `code_span` | Literal content retained; math delimiters inside are not parsed |
| Link/autolink/image | inline nodes | Destination, title, and child text retained |
| Soft/hard break | inline nodes | Distinguished as `soft_break` and `hard_break` |
| Blockquote | `blockquote` | Nested blocks retained |
| Ordered/unordered list | `list` / `list_item` | Nesting, order flag, and tight/loose state retained |
| Pipe table | `table` | Original Markdown surface retained |
| Fenced/indented code | `code_fence` / `code_block` | Language/info and literal content retained |
| Raw HTML / HTML table | `html_block` / `html_table` | HTML is opaque; tables receive a dedicated kind |
| YAML front matter | `front_matter` + metadata | Source block and parsed metadata retained |
| Reference definition | `reference_definitions` | Label, destination, and title retained separately |
| Thematic break | discarded | Consumed as a structural separator and intentionally omitted from `DocTree` and chunks |

Task-list markers currently remain text inside list items rather than a
dedicated checked-state field. Footnotes and other third-party
`markdown-it-py` extensions are opt-in plugins, not part of the default dialect.
Raw HTML is classified but its arbitrary internal DOM is not converted into
inline semantic nodes.

### Math recognition

| Syntax | Classification | Notes |
| --- | --- | --- |
| `$a+b=c$` | `math_inline` | Standard dollar-delimited inline form |
| `$ a+b=c$`, `$a+b=c $`, `$ a+b=c $` | `math_inline` | Spaces adjacent to delimiters are accepted and retained in `literal` |
| `\(a+b=c\)` | `math_inline` | Delimiter identity is retained |
| `$$...$$` on a block line | `math_block` | Single-line, multiline, matrices, aligned environments, and blank lines are opaque literal math content |
| `$$...$$ (label)` | `math_block_eqno` | Equation label retained in `attrs.eqno` |
| `\[...\]` and `\[...\] (label)` | block math | Multiline content and labels supported |

TeX content is retained as an opaque literal; Lumberjack identifies the math
element but does not validate TeX grammar or build a formula AST. Escaped
dollars, unmatched delimiters, and dollar-looking text inside code remain
non-math. Currency-shaped input such as `price $5 and $10`, `1$x$`, and `$x$2`
is deliberately not classified as math, while digits *inside* a valid formula,
such as `$2x$`, remain supported. Inline `$$...$$` embedded in prose is not part
of the current dialect; use `$...$` or `\(...\)`.

## DOCX coverage

| DOCX feature | Current behavior |
| --- | --- |
| Headings | Only explicit direct/inherited OOXML `outlineLvl` values 0-8 become section levels 1-9; names and visible numbering are never interpreted |
| Paragraph/run formatting | Paragraphs, bold, italic, and underline metadata |
| Lists | Only direct/inherited OOXML numbering definitions, including `numStyleLink`; items are grouped only when `numId`, level, and number format all match |
| Tables | Document order, nested tables, wrapped cells, escaped pipes/backslashes, and multiline cells |
| Hyperlinks/images | Relationship destination, image part, title/alt text, including table cells |
| Text boxes/drawings | Visible textbox text inside paragraph drawings is retained |
| Content controls/tracked changes | Visible `sdt`, `ins`, and `moveTo` content retained; deleted/moved-from content omitted |
| Office Math (OMML) | Inline and display equations classified as math; linear visible formula text retained |
| Provenance | Direct OOXML element paths in `SourceLocation.element_id` |
| Core properties | Title and author metadata |
| Strict OOXML | Known Strict namespaces normalized in memory before parsing |
| Damaged OPC metadata | Missing image content types, dangling optional image/thumbnail relationships, and template main types repaired in memory and reported in `metadata.docx_repairs` |

Current limits:

- Malformed `word/document.xml` is rejected. Automatically inventing content for
  mismatched XML tags would be lossy and unpredictable.
- Encrypted/password-protected documents and legacy binary `.doc` files are not
  DOCX and are unsupported.
- Headers, footers, comments, footnotes/endnotes, charts, SmartArt semantics,
  macros, and embedded OLE payloads are not emitted as body blocks.
- For markup-compatibility `AlternateContent`, the explicit `Fallback` branch
  is used. A `Choice` without a fallback is omitted rather than guessed to be
  supported.
- OMML is represented by its linear visible text, not converted losslessly into
  LaTeX or a full operator tree.
- Style names such as `Heading 2.1`, `标题 1`, `3.1.1`, `Quote`, and
  `List Bullet Custom` do not establish semantics. Similarly, monospace text is
  retained as text rather than guessed to be code.
- Packages with duplicate/unsafe part names, more than 100,000 entries, or more
  than 512 MiB total expanded content are rejected before repair or parsing.

## HTML coverage

| Input element | Representation | Current behavior |
| --- | --- | --- |
| `<h1>`-`<h6>` | `SectionNode` | Heading hierarchy; implied end tags between headings and from block content; any `</hN>` closes an open heading |
| `<title>` / `<meta>` | metadata | Routed to document metadata per the HTML5 in-head rules, never body blocks |
| Paragraphs / bare text | `paragraph` | Fragments without `<html>`/`<body>` wrappers keep all text; implicit paragraphs are bounded by recognized block tags |
| `<blockquote>` / `<pre>` | `blockquote` / `code_block` | Literal `pre` content preserved inside a fenced rendering |
| `<ul>`/`<ol>`/`<li>` | `list` / `list_item` | Nested lists stay inside their parent item; bare `<li>` without a list wrapper becomes an implicit list; `<li>` implies the end of the previous item |
| `<table>` | `html_table` | Raw table markup retained as an opaque block; nested tables tracked by depth; unclosed tables flush at end of input |
| Inline `strong`/`em`/`code`/`a`/`img` | inline nodes | Image `alt` text retained; entity references decoded |
| Block containers (`div`, `dl`, `dt`, `dd`, `section`, `figure`, ...) | soft boundary | Adjacent runs are separated the way a browser renders them instead of gluing words |
| `<script>`/`<style>` | discarded | Never emitted as body content |
| Unclosed constructs | flushed at EOF | Open headings, lists, items, tables, and blocks emit their collected content when the document ends |
| CRLF / comments / doctype | structural | Handled without affecting text or line provenance |

Known limits: formatting-element adoption (`<b>1<i>2<p>3</b>4`) keeps every
character but may join adjacent text runs, and table cell text is retained
inside the raw table markup rather than as separate inline nodes.

## Records, source, and tabular coverage

| Format | Parser | Current behavior |
| --- | --- | --- |
| Plain text / line mode | `TextParser` | Paragraph or per-line blocks with line provenance |
| Logs | `LogParser` | One atomic record per non-empty line |
| CSV / TSV | `DelimitedTextParser` | RFC 4180 quoted fields with embedded delimiters and newlines preserved; header schema in row metadata |
| JSON / YAML / TOML | `JSONParser` / `YAMLParser` / `TOMLParser` | Scalar leaves as path-aware records; empty containers as single records; invalid input rejected with `ValueError` |
| JSON Lines | `JSONLinesParser` | One canonical record per non-blank line with JSON-path provenance |
| XML | `XMLParser` | Leaf elements plus mixed-content `text()`/tail segments as ordered records with element paths |
| XLSX | `XlsxParser` | Non-empty rows as sheet-aware records; empty header cells renamed `column_N`; sheets with only headers skipped |
| SQLite | `SQLiteParser` | Table rows as records with table/row/column provenance (Python 3.11+ bytes input) |
| Python / JS / TS | `SourceCodeParser` | Top-level symbols via tree-sitter when installed, `ast`/regex fallback otherwise; malformed source returns flagged records or `ValueError` |
| Jupyter notebooks | `NotebookParser` | Non-empty cells as ordered, cell-typed records |
| SQL | `SQLParser` | Quote/comment-aware statement splitting: semicolons inside `'...'`, `"..."`, backticks, and `$$...$$` never split a statement; comment-only tails emit no records |

## Reproducible baseline

Baseline generated with seed `20260824`, at most 500 random documents per large
source, and all smaller DOCX and conformance corpora:

| Corpus/format | Selected | Result |
| --- | ---: | --- |
| Markdown element conformance | 20 | 20 successful; 58/58 element assertions |
| CommonMark 0.31.2 | 500 of 652 | 500 successful; token recall 1.0 |
| Kubernetes website Markdown | 500 of 2,453 | 500 successful; mean token recall 0.9975 |
| python-docx fixtures | 45 | 45 successful; DOCX character recall 1.0 |
| LibreOffice Writer OOXML | 377 | 376 successful; DOCX character recall 1.0 for every successful document |
| html5lib tree-construction fragments | 1,791 of 1,791 | 1,791 successful; character recall 1.0 |
| MDN Learning Area HTML | 413 of 413 | 413 successful; mean token recall 0.9992; character recall 1.0 |
| **Total** | **3,646** | **3,645 successful; one malformed-XML failure** |

Nineteen successful LibreOffice files have lexical-token recall below 0.99 because
OOXML run boundaries join or split identical visible characters differently.
Their non-whitespace-character recall is 1.0, so they are retained as a metric
diagnostic rather than reported as content loss. Likewise, 130 html5lib
fragments show token recall below 0.99 only because the test data places single
digits directly adjacent (`<a>1<p>2</a>3`); every character is retained
(character recall 1.0).

### Randomized corpus baseline

Seeded generators build documents for every parser beyond Markdown and DOCX
along with three oracles: the visible text the generator emitted, exact
element-signature counts, and — for adversarily damaged payloads — the exact
exception types the parser may reject with. Baseline generated with seed
`20260825` and 500 documents per format:

| Format family | Formats | Documents | Result |
| --- | --- | ---: | --- |
| Document | html | 500 | 500 successful; token recall 1.0 |
| Flat text | text, text-lines, log | 1,500 | 1,500 successful; token recall 1.0 |
| Delimited | csv, tsv | 1,000 | 1,000 successful; token recall 1.0 |
| Structured | json, jsonl, yaml, toml, xml | 2,500 | 2,500 successful or cleanly rejected; 0 failures |
| Tabular bytes | xlsx, sqlite | 1,000 | 1,000 successful or cleanly rejected; 0 failures |
| Source / notebooks / SQL | python, javascript, typescript, notebook, sql | 2,500 | 2,500 successful; sentinel recall 1.0 |
| **Total** | 18 formats | **9,000** | **0 failed; every strict document met recall 1.0 and exact element counts; 391 adversarial documents were cleanly rejected** |

Run the benchmarks with:

```bash
uv run python -m benchmarks.fetch_parser_corpora
uv run python -m benchmarks.parser_run \
  --seed 20260824 \
  --sample-size-per-source 500
uv run python -m benchmarks.random_run \
  --seed 20260825 \
  --documents-per-format 500
```

`raw.json` is authoritative for individual failures and diagnostics;
`summary.json` contains aggregate, per-format, and per-dataset results.
